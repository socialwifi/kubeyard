import logging
import pathlib
import os
import sys
import tempfile

import sh

import sw_cli.files_generator
from sw_cli import base_command


logger = logging.getLogger(__name__)


class InstallCompletion(base_command.BaseCommand):
    """
    Run this to enable bash completion. It writes /etc/bash_completion.d/sw-cli file. It will work automatically on
    your next bash use. You can enable it in your current sessions by running `. /etc/bash_completion.d/sw-cli`
    """
    def run(self):
        logger.info("Installing sw-cli...")
        sw_cli_dst = pathlib.Path('/etc/bash_completion.d/sw-cli')
        if sw_cli_dst.exists():
            logger.warning('File {} already exists. Skipping.'.format(str(sw_cli_dst)))
        else:
            with tempfile.NamedTemporaryFile(mode='r') as f:
                sw_cli_dst_tmp = pathlib.Path(f.name)
                sw_cli.files_generator.copy_template('sw-cli-completion.sh', sw_cli_dst_tmp, replace=True)
                sw_cli_dst_tmp.chmod(0o644)
                with sh.contrib.sudo(_with=True):
                    sh.cp(str(sw_cli_dst_tmp), str(sw_cli_dst))


class RunCompletion(base_command.BaseCommand):
    """
    Command run by script installed by `sw-cli install_bash_completion`. Shouldn't be called manually.
    It reads COMP_LINE and COMP_POINT environment variables and writes possible commands which starts with current word
    from its start to cursor position.
    """
    def run(self):
        logging.getLogger('sw_cli').setLevel('WARNING')
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
