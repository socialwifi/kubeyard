import getpass
import logging
import os
import pathlib
import re
import sys

from cached_property import cached_property
import sh

from sw_cli import settings


logger = logging.getLogger(__name__)


def cluster_factory(context):
    vm_driver = context.get('SWCLI_VM_DRIVER', settings.DEFAULT_SWCLI_VM_DRIVER)
    return CLUSTER_VM_DRIVERS[vm_driver]()


class Cluster:
    docker_env_keys = ['DOCKER_TLS_VERIFY', 'DOCKER_HOST', 'DOCKER_CERT_PATH', 'DOCKER_API_VERSION']
    minimum_minikube_version = (0, 23, 0)

    def ensure_started(self):
        if not self.is_running():
            self.start()

    def is_running(self):
        raise NotImplementedError

    def start(self):
        self._before_start()
        self._start()
        self._after_start()

    def docker_env(self):
        return {}

    def get_mounted_project_dir(self, project_dir):
        raise NotImplementedError

    def _before_start(self):
        self._check_version()

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

    def _start(self):
        raise NotImplementedError

    def _after_start(self):
        pass


class NativeLocalkubeCluster(Cluster):
    def is_running(self):
        try:
            status = sh.systemctl('is-active', 'localkube')
        except sh.ErrorReturnCode_3:
            return False
        else:
            return status.strip().lower() == 'active'

    def get_mounted_project_dir(self, project_dir):
        return project_dir

    def _start(self):
        logger.info('Starting minikube without a VM...')
        sh.sudo('-S',
                *self._start_env_as_arguments,
                'minikube', 'start',
                '--vm-driver', 'none',
                '--extra-config', 'apiserver.ServiceNodePortRange=1-32767',
                _in=self._sudo_password, _out=sys.stdout.buffer, _err=sys.stdout.buffer)

    @property
    def _start_env_as_arguments(self):
        env = {
            'MINIKUBE_HOME': os.environ['HOME'],
            'CHANGE_MINIKUBE_NONE_USER': 'true',
        }
        return ['{}={}'.format(key, value) for key, value in env.items()]

    def _after_start(self):
        super()._after_start()
        self._apply_kube_dns_fix()
        self._apply_dashboard_fix_if_needed()
        self._create_docker_registry_secret()

    @staticmethod
    def _apply_kube_dns_fix():
        """
        Fix needed on Ubuntu with systemd-resolved.
        https://github.com/kubernetes/minikube/issues/2027
        """
        logger.info('Applying kube-dns fix...')
        fix_path = pathlib.Path(__file__).parent / 'definitions' / 'kube-dns-fix'
        sh.kubectl('apply', '--record', '-f', fix_path)
        logger.info('kube-dns fix applied')

    def _apply_dashboard_fix_if_needed(self):
        """
        Fix needed on minikube 0.23.
        https://github.com/kubernetes/minikube/issues/2130
        """
        logger.info('Applying dashboard fix...')
        with sh.contrib.sudo(password=self._sudo_password, _with=True):
            dashboard_addon_path = '/etc/kubernetes/addons/dashboard-rc.yaml'
            if '1.7.0' in sh.cat(dashboard_addon_path):
                logger.info('Replacing dashboard addon file...')
                fix_path = pathlib.Path(__file__).parent / 'definitions' / 'dashboard_fix' / 'dashboard-rc.yaml'
                sh.cp(fix_path, dashboard_addon_path)
                logger.info('Dashboard addon file replaced')
            else:
                logger.info('No need to replace dashboard addon file')

    def _create_docker_registry_secret(self):
        logger.info('Creating Docker registry secret...')
        registry_name = 'docker.socialwifi.com'
        config_path = pathlib.Path.home() / '.docker' / 'config.json'
        try:
            sh.kubectl(
                'create', 'secret', 'generic',
                registry_name,
                '--from-file=.dockerconfigjson={}'.format(config_path),
                '--type=kubernetes.io/dockerconfigjson',
            )
        except sh.ErrorReturnCode as e:
            if b'already exists' not in e.stderr:
                raise e
            else:
                logger.info('Docker registry secret already exists')
        else:
            logger.info('Docker registry secret created')

    @cached_property
    def _sudo_password(self):
        prompt = "[sudo] password for %s: " % getpass.getuser()
        return getpass.getpass(prompt=prompt) + "\n"


class VirtualboxCluster(Cluster):
    def is_running(self):
        running_machines = sh.VBoxManage('list', 'runningvms')
        return 'minikube' in running_machines

    def get_mounted_project_dir(self, project_dir):
        return pathlib.Path('/hosthome') / project_dir.relative_to('/home')

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

    def docker_env(self):
        variables = map(lambda x: '$' + x, self.docker_env_keys)
        result = sh.bash('-c', 'eval $(minikube docker-env); echo "%s"' % '|'.join(variables))
        values = result.strip("\n").split('|')
        return dict(zip(self.docker_env_keys, values))


CLUSTER_VM_DRIVERS = {
    'none': NativeLocalkubeCluster,
    'virtualbox': VirtualboxCluster,
}
