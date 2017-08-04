from sw_cli import base_command
from sw_cli import commands


class HelpCommand(base_command.BaseCommand):
    """
    Shows help about commands.
    """
    def run(self):
        if self.options.command:
            for command in commands.get_all_commands():
                if command.name == self.options.command:
                    command.source.get_parser(prog='{} {}'.format(self.sw_cli_name, command.name)).print_help()
                    break
            else:
                print('Command "{}" not found!'.format(self.options.command))
                self.print_basic_help()
        else:
            print('{} is a commandline tool for easier development and deployment of Social WiFi services.'.format(
                self.sw_cli_name))
            print('For help about specific commands use {} {} <command>.'.format(self.sw_cli_name, self.command_name))
            self.print_basic_help()

    @staticmethod
    def print_basic_help():
        print('Use one of:')
        for command in commands.get_all_commands():
            print(command.name)

    def get_parser(cls, **kwargs):
        parser = super().get_parser(**kwargs)
        parser.add_argument('command', help='Command you want help for.', nargs='?')
        return parser
