import contextlib
import pathlib
import yaml
from sw_cli import context_factories, kubernetes


def setup():
    GlobalCommand().setup()


class GlobalCommand(object):
    def __init__(self):
        self.context = context_factories.GlobalContextFactory().get()

    def setup(self):
        user_context_filepath = pathlib.Path(self.context['SWCLI_USER_CONTEXT_FILEPATH'])
        with contextlib.suppress(FileExistsError):
            user_context_filepath.parent.mkdir()
        with user_context_filepath.open('w') as context_file:
            yaml.dump({
                'SWCLI_MODE': 'development',
            }, stream=context_file)
        kubernetes.Kubernetes().setup_cluster_context()
