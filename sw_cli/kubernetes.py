import contextlib
import socket

import pathlib

import collections
import sh
import yaml

from sw_cli import settings
from sw_cli import minikube


def setup_cluster_context(context):
    _get_kubernetes_commands(context).context_setup()


def install_secrets(context):
    _get_kubernetes_commands(context).install_secrets()


def _get_kubernetes_commands(context):
    if context['SWCLI_MODE'] == 'development':
        return KubernetesCommands(
            context_setup=DevelopmentKubernetesContext().setup,
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
                   '--from-literal', 'base-domain={}'.format(self.base_domain))

    @property
    def monolith_host(self):
        raise NotImplementedError

    @property
    def base_domain(self):
        raise NotImplementedError


class DevelopmentKubernetesContext(BaseKubernetesContext):
    base_domain = 'testing'

    def setup(self):
        minikube.ensure_minikube_started()
        super().setup()

    @property
    def monolith_host(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]


class ProductionKubernetesContext(BaseKubernetesContext):
    base_domain = 'socialwifi.com'
    monolith_host = 'socialwifi.com'


class BaseKubernetesSecretsInstaller:
    def __init__(self, context):
        self.context = context

    def install(self):
        command = ['create', 'secret', 'generic', self.context['KUBE_SERVICE_NAME'], '--dry-run', '-o', 'yaml']
        with contextlib.suppress(FileExistsError):
            self.secrets_path.mkdir(parents=True)
        literal_secrets = list(self._get_literal_secrets())
        file_secrets = list(self._get_file_secrets())
        if literal_secrets or file_secrets:
            for key, value in literal_secrets:
                command.append('--from-literal={}={}'.format(key, value))
            for subpath in file_secrets:
                command.append('--from-file={}'.format(subpath))
            sh.kubectl(sh.kubectl(*command), 'apply', '--record', '-f', '-')


    @property
    def yml_source_path(self):
        return self.secrets_path / 'secrets.yml'

    @property
    def secrets_path(self):
        raise NotImplementedError

    def _get_literal_secrets(self):
        if self.yml_source_path.exists():
            with self.yml_source_path.open() as yml_source:
                yield from yaml.load(yml_source).items()

    def _get_file_secrets(self):
        for subpath in self.secrets_path.iterdir():
            if subpath != self.yml_source_path:
                yield subpath


class DevelopmentKubernetesSecretsInstaller(BaseKubernetesSecretsInstaller):
    @property
    def secrets_path(self):
        return pathlib.Path(self.context['PROJECT_DIR'])/self.context['KUBERNETES_DEV_SECRETS_DIR']


class ProductionKubernetesSecretsInstaller(BaseKubernetesSecretsInstaller):
    @property
    def secrets_path(self):
        return pathlib.Path.home() / settings.KUBERNETES_PROD_SECRETS_DIR / self.context['KUBE_SERVICE_NAME']
