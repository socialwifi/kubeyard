import functools
import logging
import re
import sys

import sh


logger = logging.getLogger(__name__)

DOCKER_ENV_KEYS = ['DOCKER_TLS_VERIFY', 'DOCKER_HOST', 'DOCKER_CERT_PATH', 'DOCKER_API_VERSION']
MINIMUM_MINIKUBE_VERSION = (0, 21, 0)


def ensure_minikube_started():
    running_machines = sh.VBoxManage('list', 'runningvms')
    if 'minikube' not in running_machines:
        check_minikube_version()
        start_minikube()
        ensure_hosthome_mounted()


def check_minikube_version():
    version = str(sh.minikube('version'))
    version_pattern = r'v(\d+)\.(\d+)\.(\d+)'
    match = re.search(version_pattern, version)
    if not match:
        logger.warning('Could not determine minikube version. Got: "{}"'.format(version))
    else:
        version = tuple(map(int, match.groups()))
        if version < MINIMUM_MINIKUBE_VERSION:
            logger.warning('Minikube version {} is not supported, you may run into issues. '
                           'Minimum supported version: {}'.format(version, MINIMUM_MINIKUBE_VERSION))


def start_minikube():
    logger.info("Starting minikube...")
    minikube_iso = 'https://storage.googleapis.com/minikube/iso/minikube-v0.23.2.iso'
    sh.minikube('start',
                '--memory', '4096',
                '--iso-url', minikube_iso,
                '--docker-opt', 'storage-driver=overlay2',
                _out=sys.stdout.buffer, _err=sys.stdout.buffer)
    sh.minikube('ssh', 'sudo sysctl fs.inotify.max_user_watches=16382')


def ensure_hosthome_mounted():
    if '/hosthome' not in sh.minikube('ssh', 'mount'):
        logger.info("Preparing hosthome directory...")
        try:
            sh.minikube('ssh', 'sudo mkdir /hosthome')
        except sh.ErrorReturnCode_1 as e:
            if b'can\'t create directory \'/hosthome\': File exists' not in e.stderr:
                raise
        sh.minikube('ssh', 'sudo chmod 777 /hosthome')
        sh.minikube('ssh', 'sudo mount -t vboxsf -o uid=$(id -u),gid=$(id -g) hosthome /hosthome')


@functools.lru_cache(maxsize=1)
def docker_env():
    variables = map(lambda x: '$' + x, DOCKER_ENV_KEYS)
    result = sh.bash('-c', 'eval $(minikube docker-env); echo "%s"' % '|'.join(variables))
    values = result.strip("\n").split('|')
    return dict(zip(DOCKER_ENV_KEYS, values))
