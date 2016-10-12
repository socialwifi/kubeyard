import pathlib
import sys

import sw_cli.files_generator


def install():
    print("installing sw-cli")
    sw_cli_dst = pathlib.Path('/etc/bash_completion.d/sw-cli')
    sw_cli.files_generator.copy_template('sw-cli-completion.sh', sw_cli_dst)
    sw_cli_dst.chmod(0o644)
    print('done')


def run():
    sys.stdout.write(' '.join(get_script_names()))


def get_script_names():
    from sw_cli import commands
    for command in commands.get_all_commands():
        yield command.name
