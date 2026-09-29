import collections
import contextlib
import itertools
import json
import logging
import pathlib
import socket

import sh
import yaml

from kubeyard import context_factories
from kubeyard import kubectl as kubectl_helper
from kubeyard import minikube
from kubeyard import settings
from kubeyard import workspace

logger = logging.getLogger(__name__)


def setup_cluster_context(context, replace_configmap=False):
    _get_kubernetes_commands(context).context_setup(replace_configmap=replace_configmap)


def install_secrets(context):
    logger.info('Installing secrets...')
    _get_kubernetes_commands(context).install_secrets()
    logger.info('Secrets installed')


def install_global_secrets(context):
    logger.info('Installing global secrets...')
    for path in pathlib.Path(context['KUBEYARD_GLOBAL_SECRETS']).iterdir():
        if path.is_dir():
            GlobalSecretsInstaller(context, path.name).install()
    logger.info('Global secrets installed')


def get_global_secrets_manipulator(context, secret_name):
    return KubernetesSecretsManipulator(
        secret_name,
        pathlib.Path(context['KUBEYARD_GLOBAL_SECRETS']) / secret_name,
        context.get('KUBEYARD_NAMESPACE', ''),
    )


def _get_kubernetes_commands(context):
    if context['KUBEYARD_MODE'] == 'development':
        return KubernetesCommands(
            context_setup=DevelopmentKubernetesContext(context, context.get('KUBEYARD_NAMESPACE', '')).setup,
            install_secrets=DevelopmentKubernetesSecretsInstaller(context).install,
        )
    else:
        return KubernetesCommands(
            context_setup=ProductionKubernetesContext(context).setup,
            install_secrets=ProductionKubernetesSecretsInstaller(context).install,
        )


KubernetesCommands = collections.namedtuple('KubernetesCommand', ['context_setup', 'install_secrets'])


class BaseKubernetesContext:
    keeps_existing_configmap = False

    def __init__(self, namespace=''):
        self.namespace = namespace

    def setup(self, replace_configmap=False):
        existing = self.existing_configmap()
        if existing is not None and self.keeps_existing_configmap and not replace_configmap:
            self.report_existing_configmap(existing)
            return
        namespace_args = kubectl_helper.namespace_args(self.namespace)
        with contextlib.suppress(sh.ErrorReturnCode):
            sh.kubectl('delete', 'configmap', 'global', *namespace_args)
        sh.kubectl('create', 'configmap', 'global', *namespace_args,
                   *itertools.chain.from_iterable(
                       ('--from-literal', '{}={}'.format(key, value))
                       for key, value in self.configmap_data.items()
                   ))

    @property
    def configmap_data(self):
        return {
            'monolith-host': self.monolith_host,
            'base-domain': self.base_domain,
            'alternative-domain': self.alternative_domain,
            'debug': self.debug,
        }

    def existing_configmap(self):
        namespace_args = kubectl_helper.namespace_args(self.namespace)
        try:
            output = sh.kubectl.get.configmap('global', *namespace_args, '-o', 'json')
        except sh.ErrorReturnCode:
            return None
        return json.loads(str(output)).get('data', {})

    def report_existing_configmap(self, existing):
        logger.info('ConfigMap "global" already exists, leaving it alone.')
        differences = {
            key: (existing.get(key), value)
            for key, value in self.configmap_data.items()
            if existing.get(key) != value
        }
        if differences:
            logger.warning(
                'It differs from what kubeyard would write. Pass --replace-global-configmap to '
                'overwrite it. Differences (existing -> would be written):',
            )
            for key, (was, would_be) in sorted(differences.items()):
                logger.warning('  %s: %r -> %r', key, was, would_be)

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
    alternative_domain = 'pl-testing'
    debug = 'True'

    def __init__(self, context, namespace=''):
        super().__init__(namespace)
        self.context = context
        self.cluster = minikube.ClusterFactory().get(context)

    def setup(self, replace_configmap=False):
        self.cluster.ensure_started()
        super().setup(replace_configmap=replace_configmap)

    @property
    def base_domain(self):
        configured = context_factories.require_base_domain(self.context)
        if self.namespace.startswith(workspace.NAMESPACE_PREFIX):
            name = self.namespace[len(workspace.NAMESPACE_PREFIX):]
            return '{}.{}.{}'.format(name, workspace.DOMAIN_SEGMENT, configured)
        return configured

    @property
    def monolith_host(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]


class ProductionKubernetesContext(BaseKubernetesContext):
    debug = 'False'
    alternative_domain = 'socialwifi.pl'
    monolith_host = 'socialwifi.com'
    keeps_existing_configmap = True

    def __init__(self, context, namespace=''):
        super().__init__(namespace)
        self.context = context

    @property
    def base_domain(self):
        return context_factories.require_base_domain(self.context)


class KubernetesSecretsManipulator:
    def __init__(self, secret_name, secrets_path, namespace=''):
        self.secret_name = secret_name
        self.secrets_path = secrets_path
        self.namespace = namespace

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
                secrets = yaml.safe_load(yml_source)
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
                *kubectl_helper.namespace_args(self.namespace),
                '--output', 'yaml',
            ))
        except sh.ErrorReturnCode:
            return False
        else:
            secret = yaml.safe_load(yml_output)
            return key in secret['data']


class BaseKubernetesSecretsInstaller:
    def __init__(self, context):
        self.context = context
        self.namespace = context.get('KUBEYARD_NAMESPACE', '')

    def install(self):
        namespace_args = kubectl_helper.namespace_args(self.namespace)
        command = [
            'create', 'secret', 'generic', self.secret_name,
            *namespace_args, '--dry-run', '-o', 'yaml',
        ]
        literal_secrets = list(self.manipulator.get_literal_secrets())
        file_secrets = list(self.manipulator.get_file_secrets())
        if literal_secrets or file_secrets:
            for key, value in literal_secrets:
                command.append('--from-literal={}={}'.format(key, value))
            for subpath in file_secrets:
                command.append('--from-file={}'.format(subpath))
            sh.kubectl(sh.kubectl(*command), 'apply', *namespace_args, '--record', '-f', '-')

    @property
    def manipulator(self):
        return KubernetesSecretsManipulator(self.secret_name, self.secrets_path, self.namespace)

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
        return pathlib.Path(self.context['KUBEYARD_GLOBAL_SECRETS']) / self.secret_name
