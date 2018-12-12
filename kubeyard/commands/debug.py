from pprint import pprint

from kubeyard import base_command


class DebugCommand(base_command.InitialisedRepositoryCommand):
    """
    Prints current context.
    """
    def run(self):
        super().run()
        pprint(self.context)
