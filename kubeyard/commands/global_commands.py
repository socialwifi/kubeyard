import contextlib
import logging
import pathlib

import yaml

from kubeyard import ascii_art
from kubeyard import base_command
from kubeyard import context_factories
from kubeyard import dependencies
from kubeyard import kubernetes
from kubeyard import settings

logger = logging.getLogger(__name__)


class GlobalCommand(base_command.BaseCommand):
    @property
    def context(self):
        return context_factories.GlobalContextFactory().get()


class SetupCommand(GlobalCommand):
    """
    Set up global context. It should be run after instalation of kubeyard. By default it uses production context.
    Production context requires configured docker and kubectl. Also needs your microservices secrets to be at
    ~/kubernetes_secrets/.
    """

    def __init__(self, *, mode):
        self.mode = mode

    def run(self):
        user_context = self.get_current_user_context()
        if 'KUBEYARD_GLOBAL_SECRETS' not in user_context:
            user_context['KUBEYARD_GLOBAL_SECRETS'] = str(self.default_global_secrets_directory)
        if 'KUBEYARD_LOG_LEVEL' not in user_context:
            user_context['KUBEYARD_LOG_LEVEL'] = settings.DEFAULT_KUBEYARD_LOG_LEVEL
        if 'KUBEYARD_VM_DRIVER' not in user_context:
            user_context['KUBEYARD_VM_DRIVER'] = settings.DEFAULT_KUBEYARD_VM_DRIVER
        kubeyard_mode = self.get_kubeyard_mode()
        user_context['KUBEYARD_MODE'] = kubeyard_mode
        self.print_info(kubeyard_mode)
        with self.user_context_filepath.open('w') as context_file:
            yaml.dump(dict(user_context), stream=context_file, default_flow_style=False)
        new_context = dict(self.context, **user_context)
        kubernetes.setup_cluster_context(new_context)

    def get_current_user_context(self):
        return context_factories.GlobalContextFactory().user_context

    def get_kubeyard_mode(self):
        minikube_installed = dependencies.is_command_available('minikube')
        if self.mode == 'production':
            if minikube_installed:
                logger.error('Minikube installed! Use --development option')
                exit(1)
            else:
                return 'production'
        elif self.mode == 'development':
            if not minikube_installed:
                logger.error('Minikube not installed!')
                exit(1)
            else:
                return 'development'
        elif self.mode is None:
            return 'development' if minikube_installed else 'production'

    def print_info(self, kubeyard_mode):
        ascii_art.print_ascii_art()
        logger.info('Setting up {} mode...'.format(kubeyard_mode))

    @property
    def user_context_filepath(self):
        user_context_filepath = pathlib.Path(self.context['KUBEYARD_USER_CONTEXT_FILEPATH'])
        with contextlib.suppress(FileExistsError):
            user_context_filepath.parent.mkdir()
        return user_context_filepath

    @property
    def default_global_secrets_directory(self):
        global_secrets = self.user_context_filepath.parent / 'global-secrets/'
        with contextlib.suppress(FileExistsError):
            global_secrets.mkdir()
        return global_secrets


class InstallGlobalSecretsCommand(GlobalCommand):
    """
    Installs secrets from global secrets directory (usualy from ~/.kubeyard/global-secrets/).
    Usually secrets are maintained per microservice.
    Some secrets are easier to maintain if they are in one global file.

    In example: redis databases.
    """

    def run(self):
        kubernetes.install_global_secrets(self.context)
