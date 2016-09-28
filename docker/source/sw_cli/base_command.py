from optparse import OptionParser

import pathlib
from sw_cli import settings
from sw_cli import context_factories

parser = OptionParser()
parser.add_option("--directory", dest="directory", default=settings.DEFAULT_SWCLI_PROJECT_DIR,
                  help="Select project root directory.")


class CommandException(Exception):
    pass


class BaseCommand(object):
    def __init__(self):
        options, args = parser.parse_args()
        self.project_dir = pathlib.Path(options.directory).resolve()
        try:
            self.context = context_factories.InitialisedRepoContextFactory(self.project_dir).get()
        except FileNotFoundError:
            print("Invalid project root directory: %s. Exiting.." % self.project_dir)
            exit(1)
