import io
import logging
import os
import sys

import sh

from sw_cli.commands.devel import BaseDevelCommand

logger = logging.getLogger(__name__)


class UpdateRequirementsCommand(BaseDevelCommand):
    """
    Updates docker/requirements/python.txt file based on docker/source/base_requirements.txt.
    In container it creates virtualenv and runs:

        pip install -r docker/source/base_requirements.txt && pip freeze > docker/source/base_requirements.txt

    Can be overridden in <project_dir>/sripts/update_requirements.

    If sw-cli is set up in development mode it uses minikube as docker host.
    """
    custom_script_name = 'update_requirements'
    context_vars = ['use_legacy_pip']

    def __init__(self, use_legacy_pip=False, **kwargs):
        super().__init__(**kwargs)
        self.use_legacy_pip = use_legacy_pip

    def run_default(self):
        logger.info('Updating requirements for "{}"...'.format(self.image))
        if self.use_legacy_pip is True:
            os.system(self.legacy_pip_freeze_command)
        else:
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
                    '-e', 'CUSTOM_COMPILE_COMMAND="sw-cli update_requirements"',
                    self.image, 'freeze_requirements',
                    _in=input, _out=output, _err=sys.stdout.buffer)
        return output.getvalue()
