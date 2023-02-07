import datetime
import getpass
import logging
import pathlib
import re
import sys
import time

import sh

from cached_property import cached_property

from kubeyard import settings

logger = logging.getLogger(__name__)


class Cluster:
    docker_env_keys = ['DOCKER_TLS_VERIFY', 'DOCKER_HOST', 'DOCKER_CERT_PATH', 'DOCKER_API_VERSION']
    minimum_minikube_version = (1, 29, 0)

    def ensure_started(self):
        if not self.is_running():
            self.start()

    def is_running(self):
        raise NotImplementedError

    def start(self):
        self._before_start()
        self._start()
        self._after_start()

    def _before_start(self):
        self._check_version()

    def _start(self):
        raise NotImplementedError

    def _after_start(self):
        pass

    def docker_env(self):
        return {}

    def get_mounted_project_dir(self, project_dir):
        raise NotImplementedError

    def _check_version(self):
        version = str(sh.minikube('version'))
        version_pattern = r'v(\d+)\.(\d+)\.(\d+)'
        match = re.search(version_pattern, version)
        if not match:
            logger.warning('Could not determine minikube version. Got: "{}"'.format(version))
        else:
            version = tuple(map(int, match.groups()))
            if version < self.minimum_minikube_version:
                logger.warning('Minikube version {} is not supported, you may run into issues. '
                               'Minimum supported version: {}'.format(version, self.minimum_minikube_version))


class NativeLocalkubeCluster(Cluster):
    _docker_config_path = '/etc/docker/daemon.json'

    def __init__(self):
        self._docker_config_backup_path = f'{self._docker_config_path}_backup_{datetime.datetime.now().isoformat()}'

    def is_running(self):
        try:
            status = sh.systemctl('is-active', 'kubelet')
        except sh.ErrorReturnCode_3:
            return False
        else:
            return status.strip().lower() == 'active'

    def _before_start(self):
        super()._before_start()
        self._backup_docker_config()

    # minikube overrides contents of /etc/docker/daemon.json with settings that
    # shouldn't make any difference for us, but it breaks all custom modifications like "data-root"
    def _backup_docker_config(self):
        logger.info('Creating docker config file backup...')
        with sh.contrib.sudo(password=self._sudo_password, _with=True):
            sh.cp('-a', self._docker_config_path, self._docker_config_backup_path)
        logger.info('Docker config file backup created.')

    def _start(self):
        logger.info('Starting minikube without a VM...')
        sh.sudo('-E', '-S',
                *self._start_env_as_arguments,
                'minikube', 'start',
                '--driver', 'none',
                '--container-runtime', 'docker',
                '--kubernetes-version', 'v1.21.14',
                '--extra-config', 'apiserver.service-node-port-range=1-32767',
                _in=self._sudo_password, _out=sys.stdout.buffer, _err=sys.stdout.buffer)

    def _after_start(self):
        super()._after_start()
        self._restore_docker_config()
        self._handle_persistent_storage()

    def _restore_docker_config(self):
        logger.info('Restoring docker config file...')
        with sh.contrib.sudo(password=self._sudo_password, _with=True):
            sh.mv(self._docker_config_backup_path, self._docker_config_path)
            sh.systemctl('restart', 'docker.service')
        logger.info('(sleep 20s.) Docker config file restored, waiting for minikube to reconcile '
                    'after Docker restart...')
        time.sleep(20)
        logger.info('Waiting done.')

    # https://github.com/kubernetes/minikube/issues/14034#issuecomment-1107845713
    def _handle_persistent_storage(self):
        self._bind_mount('/tmp/hostpath-provisioner', '/var/lib/minikube_persistence/hostpath-provisioner')
        self._bind_mount('/tmp/hostpath_pv', '/var/lib/minikube_persistence/hostpath_pv')

    def _bind_mount(self, source_dir, destination_dir):
        if self._bind_mount_exists(destination_dir):
            return
        with sh.contrib.sudo(password=self._sudo_password, _with=True):
            sh.mkdir('-p', destination_dir)
            sh.rm('-rf', source_dir)
            sh.mkdir(source_dir)
            sh.mount('--bind', source_dir, destination_dir)

    def _bind_mount_exists(self, path):
        try:
            sh.mountpoint('-q', path)
        except (sh.ErrorReturnCode_1, sh.ErrorReturnCode_32):
            return False
        else:
            return True

    def get_mounted_project_dir(self, project_dir):
        return project_dir

    @property
    def _start_env_as_arguments(self):
        env = {
            'CHANGE_MINIKUBE_NONE_USER': 'true',
        }
        return ['{}={}'.format(key, value) for key, value in env.items()]

    @cached_property
    def _sudo_password(self):
        prompt = "[sudo] password for %s: " % getpass.getuser()
        return getpass.getpass(prompt=prompt) + "\n"


class VirtualboxCluster(Cluster):
    def is_running(self):
        running_machines = sh.VBoxManage('list', 'runningvms')
        return 'minikube' in running_machines

    def _start(self):
        logger.info('Starting minikube with VirtualBox...')
        minikube_iso = 'https://storage.googleapis.com/minikube/iso/minikube-v0.23.4.iso'
        sh.minikube('start',
                    '--memory', '4096',
                    '--disk-size', '30g',
                    '--iso-url', minikube_iso,
                    '--docker-opt', 'storage-driver=overlay2',
                    _out=sys.stdout.buffer, _err=sys.stdout.buffer)

    def _after_start(self):
        super()._after_start()
        self._increase_inotify_limit()
        self._ensure_hosthome_mounted()

    def _increase_inotify_limit(self):
        sh.minikube('ssh', 'sudo sysctl fs.inotify.max_user_watches=16382')

    def _ensure_hosthome_mounted(self):
        if '/hosthome' not in sh.minikube('ssh', 'mount'):
            logger.info("Preparing hosthome directory...")
            try:
                sh.minikube('ssh', 'sudo mkdir /hosthome')
            except sh.ErrorReturnCode_1 as e:
                if b'can\'t create directory \'/hosthome\': File exists' not in e.stderr:
                    raise
            sh.minikube('ssh', 'sudo chmod 777 /hosthome')
            sh.minikube('ssh', 'sudo mount -t vboxsf -o uid=$(id -u),gid=$(id -g) hosthome /hosthome')

    def get_mounted_project_dir(self, project_dir):
        return pathlib.Path('/hosthome') / project_dir.relative_to('/home')

    def docker_env(self):
        variables = map(lambda x: '$' + x, self.docker_env_keys)
        result = sh.bash('-c', 'eval $(minikube docker-env); echo "%s"' % '|'.join(variables))
        values = result.strip("\n").split('|')
        return dict(zip(self.docker_env_keys, values))


class ClusterFactory:
    VM_DRIVERS = {
        'none': NativeLocalkubeCluster,
        'virtualbox': VirtualboxCluster,
    }

    def get(self, context):
        vm_driver = context.get('KUBEYARD_VM_DRIVER', settings.DEFAULT_KUBEYARD_VM_DRIVER)
        return self.VM_DRIVERS[vm_driver]()
