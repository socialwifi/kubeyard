from argparse import ArgumentParser
import pathlib

from cached_property import cached_property

from sw_cli import settings
from sw_cli import context_factories


class CommandException(Exception):
    pass


class BaseCommand:
    def __init__(self, args):
        self.args = args

    def run(self):
        raise NotImplementedError

    @cached_property
    def options(self):
        parser = self.get_parser()
        return parser.parse_args(self.args)

    @classmethod
    def get_parser(cls):
        return ArgumentParser()


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
    def get_parser(cls):
        parser = super().get_parser()
        parser.add_argument("--directory", dest="directory", default=settings.DEFAULT_SWCLI_PROJECT_DIR,
                            help="Select project root directory.")
        return parser
