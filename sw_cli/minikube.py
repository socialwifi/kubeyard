import logging
import pathlib
import re
import sys

import sh

from sw_cli import settings


logger = logging.getLogger(__name__)


def cluster_factory(context):
    vm_driver = context.get('SWCLI_VM_DRIVER', settings.DEFAULT_SWCLI_VM_DRIVER)
    return CLUSTER_VM_DRIVERS[vm_driver]()


class Cluster:
    docker_env_keys = ['DOCKER_TLS_VERIFY', 'DOCKER_HOST', 'DOCKER_CERT_PATH', 'DOCKER_API_VERSION']
    minimum_minikube_version = (0, 21, 0)

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


class VirtualboxCluster(Cluster):
    def is_running(self):
        running_machines = sh.VBoxManage('list', 'runningvms')
        return 'minikube' in running_machines

    def get_mounted_project_dir(self, project_dir):
        return pathlib.Path('/hosthome') / project_dir.relative_to('/home')

    def _start(self):
        logger.info("Starting minikube...")
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
    'virtualbox': VirtualboxCluster,
}
