#!/usr/bin/env python

import os
import sys

from sw_cli import commands
from sw_cli import logging
from sw_cli.commands import help


def run():
    logging.init_logging()
    try:
        command_name = sys.argv[1]
        sw_cli_name = os.path.basename(sys.argv[0])
    except (KeyError, IndexError):
        help.HelpCommand.print_basic_help()
    else:
        run_command(command_name, sw_cli_name, sys.argv[2:])


def run_command(command_name, sw_cli_name, arguments):
    for command in commands.get_all_commands():
        if command_name == command.name:
            command.source(sw_cli_name, command_name, arguments, **command.kwargs).run()
            print('Done')
            break
    else:
        help.HelpCommand.print_basic_help()
        exit(1)


if __name__ == '__main__':
    run()
