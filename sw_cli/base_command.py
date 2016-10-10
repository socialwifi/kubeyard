from optparse import OptionParser
import pathlib

from cached_property import cached_property

from sw_cli import settings
from sw_cli import context_factories


class CommandException(Exception):
    pass


class BaseCommand(object):
    @cached_property
    def context(self):
        try:
            return context_factories.InitialisedRepoContextFactory(self.project_dir).get()
        except FileNotFoundError:
            print("Invalid project root directory: %s. Exiting.." % self.project_dir)
            exit(1)

    @cached_property
    def project_dir(self):
        return pathlib.Path(self.options.directory).resolve()

    @property
    def options(self):
        return self._parser_results[0]

    @property
    def args(self):
        return self._parser_results[1]

    @cached_property
    def _parser_results(self):
        parser = self.get_parser()
        return parser.parse_args()

    def get_parser(self):
        parser = OptionParser()
        parser.add_option("--directory", dest="directory", default=settings.DEFAULT_SWCLI_PROJECT_DIR,
                          help="Select project root directory.")
        return parser
