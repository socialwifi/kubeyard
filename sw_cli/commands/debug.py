from pprint import pprint

from sw_cli import base_command


class DebugCommand(base_command.InitialisedRepositoryCommand):
    def run(self):
        pprint(self.context)
