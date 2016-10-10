import functools

import sh

DOCKER_ENV_KEYS = ['DOCKER_TLS_VERIFY', 'DOCKER_HOST', 'DOCKER_CERT_PATH', 'DOCKER_API_VERSION']


def ensure_minikube_started():
    status = sh.minikube('status', '--format={{.MinikubeStatus}}')
    if status.strip().lower() != 'running':
        print("Starting minikube...")
        sh.minikube('start')


@functools.lru_cache(maxsize=1)
def docker_env():
    variables = map(lambda x: '$' + x, DOCKER_ENV_KEYS)
    result = sh.bash('-c', 'eval $(minikube docker-env); echo "%s"' % '|'.join(variables))
    values = result.strip("\n").split('|')
    return dict(zip(DOCKER_ENV_KEYS, values))
