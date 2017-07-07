#!/usr/bin/env python

import sys

from sw_cli import commands


def run():
    try:
        command_name = sys.argv[1]
    except (KeyError, IndexError):
        print_usage()
    else:
        run_command(command_name, sys.argv[2:])


def run_command(command_name, arguments):
    for command in commands.get_all_commands():
        if command_name == command.name:
            try:
                command.source(arguments)
                break
            except commands.devel.SilencedException as e:
                exit(e.code)
    else:
        print_usage()
        exit(1)


def print_usage():
    print('Use one of:')
    for command in commands.get_all_commands():
        print(command.name)


if __name__ == '__main__':
    run()
