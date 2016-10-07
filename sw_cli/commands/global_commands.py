import contextlib
import pathlib
from optparse import OptionParser

import yaml
from sw_cli import context_factories, kubernetes


def setup():
    GlobalCommand().setup()


class GlobalCommand(object):
    def __init__(self):
        self.context = context_factories.GlobalContextFactory().get()
        parser = self.get_parser()
        self.options, self.args = parser.parse_args()

    def setup(self):
        user_context_filepath = pathlib.Path(self.context['SWCLI_USER_CONTEXT_FILEPATH'])
        with contextlib.suppress(FileExistsError):
            user_context_filepath.parent.mkdir()
        with user_context_filepath.open('w') as context_file:
            yaml.dump({
                'SWCLI_MODE': self.options.mode,
            }, stream=context_file)
        kubernetes.Kubernetes().setup_cluster_context()

    def get_parser(self):
        parser = OptionParser()
        parser.add_option("--development", dest="mode", default='production', action='store_const', const='development',
                          help="Select project root directory.")
        return parser
