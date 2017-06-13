import pathlib
import os
import sys

import sw_cli.files_generator


def install(args):
    print("Installing sw-cli...")
    sw_cli_dst = pathlib.Path('/etc/bash_completion.d/sw-cli')
    sw_cli.files_generator.copy_template('sw-cli-completion.sh', sw_cli_dst)
    sw_cli_dst.chmod(0o644)
    print('Done.')


def run(args):
    line = os.environ.get('COMP_LINE', '')
    point = int(os.environ.get('COMP_POINT', '0'))
    prefix = line[:point].split(' ')[-1]
    script_names = get_script_names()
    filtered = [name for name in script_names if name.startswith(prefix)]
    sys.stdout.write(' '.join(filtered))


def get_script_names():
    from sw_cli import commands
    for command in commands.get_all_commands():
        yield command.name
