import functools

import sh

DOCKER_ENV_KEYS = ['DOCKER_TLS_VERIFY', 'DOCKER_HOST', 'DOCKER_CERT_PATH', 'DOCKER_API_VERSION']


def ensure_minikube_set_up():
    ensure_minikube_started()
    ensure_hosthome_mounted()


def ensure_minikube_started():
    status = sh.minikube('status', '--format={{.MinikubeStatus}}')
    if status.strip().lower() != 'running':
        print("Starting minikube...")
        sh.minikube('start', '--memory', '4096')
        sh.minikube('ssh', 'sudo sysctl fs.inotify.max_user_watches=16382')


def ensure_hosthome_mounted():
    if '/hosthome' not in sh.minikube('ssh', 'mount'):
        print("Preparing hosthome directory...")
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
