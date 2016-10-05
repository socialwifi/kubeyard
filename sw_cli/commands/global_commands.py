import yaml
from sw_cli import context_factories
from sw_cli import io_utils


def configure_user_context():
    GlobalCommand().configure_user_context()


class GlobalCommand(object):
    def __init__(self):
        self.context = context_factories.GlobalContextFactory().get()

    def configure_user_context(self):
        mode = io_utils.default_input('mode', 'development')
        with open(self.context['SWCLI_USER_CONTEXT_FILEPATH']) as context_file:
            yaml.dump({
                'SWCLI_MODE': mode,
            }, stream=context_file)
