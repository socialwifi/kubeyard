import io
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

    You must use --generic to do that. In future release this flag become default.

    Can be overridden in <project_dir>/sripts/update_requirements.
    """
    custom_script_name = 'update_requirements'

    def __init__(self, generic=False, **kwargs):
        super().__init__(**kwargs)
        self.generic = generic

    def run_default(self):
        logger.info('Updating requirements for "{}"...'.format(self.image))
        if self.generic:
            self.update_generic()
            logger.info('Requirements updated!')
        else:
            logger.warning(
                'Deprecated method! '
                'You should integrate "freeze_requirements" command in application image and use "--generic flag".',
            )
            with open("docker/requirements/python.txt", "w") as output_file:
                output_file.write(self.get_pip_freeze_output())
            logger.info('Requirements updated and saved to "docker/requirements/python.txt"')

    @property
    def legacy_pip_freeze_command(self):
        return ('(cat docker/source/base_requirements.txt | docker run --rm -i python:3.6.0'
                ' bash -c "'
                'pip install --upgrade setuptools==34.3.0 > /dev/stderr ; '
                'pip install -r /dev/stdin > /dev/stderr ; '
                'pip freeze")'
                ' > docker/requirements.txt')

    def get_pip_freeze_output(self):
        output = io.StringIO()
        input = sh.cat("docker/source/base_requirements.txt")
        self.docker('run', '--rm', '-i',
                    '-e', 'CUSTOM_COMPILE_COMMAND="kubeyard update_requirements"',
                    self.image, 'freeze_requirements',
                    _in=input, _out=output, _err=sys.stdout.buffer)
        return output.getvalue()

    def update_generic(self):
        sh.docker(
            'run', '--rm', '-i',
            '-u', '{}:{}'.format(self.uid, self.gid),
            '-e', 'CUSTOM_COMPILE_COMMAND="kubeyard update_requirements"',
            '-e', 'HOME=/tmp',
            *self.volumes,
            self.image,
            'bash', '-c', 'freeze_requirements',
            _err=sys.stdout.buffer,
        )
