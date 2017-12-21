import contextlib
import logging
import socket

import pathlib

import collections
import sh
import yaml

from sw_cli import settings
from sw_cli import minikube


logger = logging.getLogger(__name__)


def setup_cluster_context(context):
    _get_kubernetes_commands(context).context_setup()


def install_secrets(context):
    logger.info('Installing secrets...')
    _get_kubernetes_commands(context).install_secrets()
    logger.info('Secrets installed')


def install_global_secrets(context):
    logger.info('Installing global secrets...')
    for path in pathlib.Path(context['SWCLI_GLOBAL_SECRETS']).iterdir():
        if path.is_dir():
            GlobalSecretsInstaller(context, path.name).install()
    logger.info('Global secrets installed')


def get_global_secrets_manipulator(context, secret_name):
    return KubernetesSecretsManipulator(
        secret_name,
        pathlib.Path(context['SWCLI_GLOBAL_SECRETS']) / secret_name
    )


def _get_kubernetes_commands(context):
    if context['SWCLI_MODE'] == 'development':
        return KubernetesCommands(
            context_setup=DevelopmentKubernetesContext(context).setup,
            install_secrets=DevelopmentKubernetesSecretsInstaller(context).install,
        )
    else:
        return KubernetesCommands(
            context_setup=ProductionKubernetesContext().setup,
            install_secrets=ProductionKubernetesSecretsInstaller(context).install,
        )

KubernetesCommands = collections.namedtuple('KubernetesCommand', ['context_setup', 'install_secrets'])


class BaseKubernetesContext:
    def setup(self):
        with contextlib.suppress(sh.ErrorReturnCode):
            sh.kubectl('delete', 'configmap', 'global')
        sh.kubectl('create', 'configmap', 'global',
                   '--from-literal', 'monolith-host={}'.format(self.monolith_host),
                   '--from-literal', 'base-domain={}'.format(self.base_domain),
                   '--from-literal', 'alternative-domain={}'.format(self.alternative_domain),
                   '--from-literal', 'debug={}'.format(self.debug),
                   )

    @property
    def monolith_host(self):
        raise NotImplementedError

    @property
    def base_domain(self):
        raise NotImplementedError

    @property
    def alternative_domain(self):
        raise NotImplementedError

    @property
    def debug(self):
        raise NotImplementedError


class DevelopmentKubernetesContext(BaseKubernetesContext):
    base_domain = 'testing'
    alternative_domain = 'pl-testing'
    debug = 'True'

    def __init__(self, context):
        self.cluster = minikube.ClusterFactory().get(context)

    def setup(self):
        self.cluster.ensure_started()
        super().setup()

    @property
    def monolith_host(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]


class ProductionKubernetesContext(BaseKubernetesContext):
    debug = 'False'
    base_domain = 'socialwifi.com'
    alternative_domain = 'socialwifi.pl'
    monolith_host = 'socialwifi.com'


class KubernetesSecretsManipulator:
    def __init__(self, secret_name, secrets_path):
        self.secret_name = secret_name
        self.secrets_path = secrets_path

    @property
    def yml_source_path(self):
        return self.secrets_path / 'secrets.yml'

    def get_literal_secrets(self):
        return self.get_literal_secrets_mapping().items()

    def get_file_secrets(self):
        self._ensure_path_exists()
        for subpath in self.secrets_path.iterdir():
            if subpath != self.yml_source_path:
                yield subpath

    def set_literal_secret(self, key, value):
        self._ensure_path_exists()
        literal_secrets = self.get_literal_secrets_mapping()
        literal_secrets[key] = value
        with self.yml_source_path.open('w+') as yml_source:
            yaml.dump(literal_secrets, yml_source)

    def get_literal_secrets_mapping(self):
        if self.yml_source_path.exists():
            with self.yml_source_path.open() as yml_source:
                secrets = yaml.load(yml_source)
            return secrets or {}
        else:
            return {}

    def _ensure_path_exists(self):
        with contextlib.suppress(FileExistsError):
            self.secrets_path.mkdir(parents=True)

    def is_key_present(self, key):
        try:
            yml_output = str(sh.kubectl(
                'get', 'secrets', self.secret_name,
                '--output', 'yaml'
            ))
        except sh.ErrorReturnCode:
            return False
        else:
            secret = yaml.load(yml_output)
            return key in secret['data']


class BaseKubernetesSecretsInstaller:
    def __init__(self, context):
        self.context = context

    def install(self):
        command = ['create', 'secret', 'generic', self.secret_name, '--dry-run', '-o', 'yaml']
        literal_secrets = list(self.manipulator.get_literal_secrets())
        file_secrets = list(self.manipulator.get_file_secrets())
        if literal_secrets or file_secrets:
            for key, value in literal_secrets:
                command.append('--from-literal={}={}'.format(key, value))
            for subpath in file_secrets:
                command.append('--from-file={}'.format(subpath))
            sh.kubectl(sh.kubectl(*command), 'apply', '--record', '-f', '-')

    @property
    def manipulator(self):
        return KubernetesSecretsManipulator(self.secret_name, self.secrets_path)

    @property
    def secret_name(self):
        raise NotImplementedError

    @property
    def secrets_path(self):
        raise NotImplementedError



class BaseProjectKubernetesSecretsInstaller(BaseKubernetesSecretsInstaller):
    @property
    def secret_name(self):
        return self.context['KUBE_SERVICE_NAME']


class DevelopmentKubernetesSecretsInstaller(BaseProjectKubernetesSecretsInstaller):
    @property
    def secrets_path(self):
        return pathlib.Path(self.context['PROJECT_DIR'])/self.context['KUBERNETES_DEV_SECRETS_DIR']


class ProductionKubernetesSecretsInstaller(BaseProjectKubernetesSecretsInstaller):
    @property
    def secrets_path(self):
        return pathlib.Path.home() / settings.KUBERNETES_PROD_SECRETS_DIR / self.secret_name


class GlobalSecretsInstaller(BaseKubernetesSecretsInstaller):
    secret_name = None

    def __init__(self, context, secret_name):
        super().__init__(context)
        self.secret_name = secret_name

    @property
    def secrets_path(self):
        return pathlib.Path(self.context['SWCLI_GLOBAL_SECRETS']) / self.secret_name
