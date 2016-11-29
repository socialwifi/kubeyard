from argparse import ArgumentParser
import contextlib
import pathlib

import yaml
from sw_cli import context_factories, kubernetes


def setup(args):
    GlobalCommand(args).setup()


class GlobalCommand:
    def __init__(self, args):
        self.context = context_factories.GlobalContextFactory().get()
        parser = self.get_parser()
        self.options = parser.parse_args(args)

    def setup(self):
        user_context = self.get_current_user_context()
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

    def get_parser(self):
        parser = ArgumentParser()
        parser.add_argument("--development", dest="mode", default='production', action='store_const',
                            const='development', help="Select project root directory.")
        return parser
