from pprint import pprint

from kubeyard import base_command


class DebugCommand(base_command.InitialisedRepositoryCommand):
    """
    Prints current context.

    If NAME supplied prints value of the single variable instead of dict containing whole context.
    """
    def __init__(self, name, **kwargs):
        super().__init__(**kwargs)
        self.name = name

    def run(self):
        super().run()
        if self.name is not None:
            print(self.context.get(self.name.upper()))
        else:
            pprint(self.context)
