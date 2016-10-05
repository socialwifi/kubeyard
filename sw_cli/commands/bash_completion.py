import sys


def run():
    sys.stdout.write(' '.join(get_script_names()))


def get_script_names():
    from sw_cli import commands
    for command in commands.get_all_commands():
        yield command.name
