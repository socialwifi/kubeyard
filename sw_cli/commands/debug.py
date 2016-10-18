from pprint import pprint

from sw_cli import base_command


class DebugCommand(base_command.BaseCommand):
    def show_variables(self):
        pprint(self.context)


def variables(args):
    cmd = DebugCommand(args)
    cmd.show_variables()
