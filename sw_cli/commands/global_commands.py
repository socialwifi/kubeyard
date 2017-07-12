import contextlib
import pathlib

import yaml

from sw_cli import base_command
from sw_cli import context_factories
from sw_cli import kubernetes


class GlobalCommand(base_command.BaseCommand):
    @property
    def context(self):
        return context_factories.GlobalContextFactory().get()


class SetupCommand(GlobalCommand):
    """
    Set up global context. It should be run after instalation of sw-cli. By default it uses production context.
    Production context requires configured docker and kubectl. Also needs your microservices secrets to be at
    ~/kubernetes_secrets/.
    """
    def run(self):
        user_context = self.get_current_user_context()
        if 'SWCLI_GLOBAL_SECRETS' not in user_context:
            user_context['SWCLI_GLOBAL_SECRETS'] = str(self.default_global_secrets_directory)
        user_context['SWCLI_MODE'] = self.options.mode
        with self.user_context_filepath.open('w') as context_file:
            yaml.dump(user_context, stream=context_file)
        new_context = dict(self.context, **user_context)
        kubernetes.setup_cluster_context(new_context)

    def get_current_user_context(self):
        return context_factories.GlobalContextFactory().user_context

    @property
    def user_context_filepath(self):
        user_context_filepath = pathlib.Path(self.context['SWCLI_USER_CONTEXT_FILEPATH'])
        with contextlib.suppress(FileExistsError):
            user_context_filepath.parent.mkdir()
        return user_context_filepath

    @property
    def default_global_secrets_directory(self):
        global_secrets = self.user_context_filepath.parent / 'global-secrets/'
        with contextlib.suppress(FileExistsError):
            global_secrets.mkdir()
        return global_secrets

    @classmethod
    def get_parser(cls, **kwargs):
        parser = super().get_parser(**kwargs)
        parser.add_argument("--development", dest="mode", default='production', action='store_const',
                            const='development', help="Sets development context using minikube. Development context "
                                                      "uses secrets from repository.")
        return parser


class InstallGlobalSecretsCommand(GlobalCommand):
    """
    Installs secrets from global secrets directory (usualy from ~/.sw_cli/global-secrets/).
    Usualy secrets are maintained per microservice. Some secrets are easier to maintain if they are in one global file.
    In example: redis databases.
    """
    def run(self):
        kubernetes.install_global_secrets(self.context)
