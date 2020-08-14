import logging
import sys

import sh

from kubeyard.commands.devel import BaseDevelCommand

logger = logging.getLogger(__name__)


class UpdateRequirementsCommand(BaseDevelCommand):
    """
    Command can update requirements using `freeze_requirements` command in container.

    Requirements: \n
        - `freeze_requirements command` available in container \n
        - volume with requirements files mounted \n

    Can be overridden in <project_dir>/scripts/update_requirements.
    """
    custom_script_name = 'update_requirements'

    def run_default(self):
        logger.info('Updating requirements for "{}"...'.format(self.image))
        sh.docker(
            'run', '--rm', '-i',
            '-u', '{}:{}'.format(self.uid, self.gid),
            '-e', 'CUSTOM_COMPILE_COMMAND="kubeyard update_requirements"',
            '-e', 'HOME=/tmp',
            *self.volumes,
            self.image,
            'bash', '-c', 'freeze_requirements',
            _out=sys.stdout.buffer,
            _err=sys.stdout.buffer,
        )
        logger.info('Requirements updated!')
