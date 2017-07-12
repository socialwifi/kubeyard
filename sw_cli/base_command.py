from argparse import ArgumentParser
import pathlib

from cached_property import cached_property

from sw_cli import settings
from sw_cli import context_factories


class CommandException(Exception):
    pass


class BaseCommand:
    def __init__(self, sw_cli_name, command_name, args):
        self.sw_cli_name = sw_cli_name
        self.command_name = command_name
        self.args = args

    def run(self):
        raise NotImplementedError

    @cached_property
    def options(self):
        parser = self.get_parser(prog='{} {}'.format(self.sw_cli_name, self.command_name))
        return parser.parse_args(self.args)

    @classmethod
    def get_parser(cls, **kwargs):
        return ArgumentParser(description=cls.__doc__, **kwargs)


class InitialisedRepositoryCommand(BaseCommand):
    @cached_property
    def context(self):
        try:
            return context_factories.InitialisedRepoContextFactory(self.project_dir).get()
        except FileNotFoundError:
            print("Invalid project root directory: %s. Exiting." % self.project_dir)
            exit(1)

    @cached_property
    def project_dir(self):
        return pathlib.Path(self.options.directory).resolve()

    @classmethod
    def get_parser(cls, **kwargs):
        parser = super().get_parser(**kwargs)
        parser.add_argument("--directory", dest="directory", default=settings.DEFAULT_SWCLI_PROJECT_DIR,
                            help="Select project root directory.")
        return parser
