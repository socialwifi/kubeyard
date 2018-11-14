import logging
import pathlib
import tempfile

import sh

import sw_cli.files_generator
from sw_cli import base_command

logger = logging.getLogger(__name__)


class InstallCompletion(base_command.BaseCommand):
    """
    Run this to enable bash completion. It writes /etc/bash_completion.d/sw-cli file.
    It will work automatically on your next bash use.

    You can enable it in your current sessions by running `. /etc/bash_completion.d/sw-cli`
    """
    sw_cli_dst = pathlib.Path('/etc/bash_completion.d/sw-cli')

    def __init__(self, *, force):
        self.force = force

    def run(self):
        logger.info("Installing sw-cli...")
        if self.sw_cli_dst.exists() and not self.force:
            logger.warning('File {} already exists. Skipping.'.format(str(self.sw_cli_dst)))
        else:
            with tempfile.NamedTemporaryFile(mode='r') as f:
                sw_cli_dst_tmp = pathlib.Path(f.name)
                sw_cli.files_generator.copy_template('sw-cli-completion.sh', sw_cli_dst_tmp, replace=True)
                sw_cli_dst_tmp.chmod(0o644)
                with sh.contrib.sudo(_with=True):
                    sh.cp(str(sw_cli_dst_tmp), str(self.sw_cli_dst))


def get_script_names():
    from sw_cli import commands
    for command in commands.get_all_commands():
        yield command.name
