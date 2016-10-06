from optparse import OptionParser

import pathlib
from sw_cli import settings
from sw_cli import context_factories


class CommandException(Exception):
    pass


class BaseCommand(object):
    def __init__(self):
        parser = self.get_parser()
        self.options, self.args = parser.parse_args()
        self.project_dir = pathlib.Path(self.options.directory).resolve()
        try:
            self.context = context_factories.InitialisedRepoContextFactory(self.project_dir).get()
        except FileNotFoundError:
            print("Invalid project root directory: %s. Exiting.." % self.project_dir)
            exit(1)

    def get_parser(self):
        parser = OptionParser()
        parser.add_option("--directory", dest="directory", default=settings.DEFAULT_SWCLI_PROJECT_DIR,
                          help="Select project root directory.")
        return parser
