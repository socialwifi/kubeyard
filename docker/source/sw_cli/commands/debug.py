from pprint import pprint

from sw_cli import base_command


class DebugCommand(base_command.BaseCommand):
    def show_variables(self):
        pprint(self.context)


def variables():
    cmd = DebugCommand()
    cmd.show_variables()
