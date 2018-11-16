import logging
import sys
import typing

import sh

from sw_cli.commands.devel import BaseDevelCommand

logger = logging.getLogger(__name__)


class FixCodeStyleCommand(BaseDevelCommand):
    """
    Fix code style.

    Image should have `fix_code_style` command available.

    You also need to configure volumes to apply changes to code on your machine.
    """
    custom_script_name = 'fix_code_style'

    @property
    def volumes(self) -> typing.Iterable[str]:
        if self.is_development:
            mounted_project_dir = self.cluster.get_mounted_project_dir(self.project_dir)
            for volume in self.context.get('DEV_MOUNTED_PATHS', []):
                if 'mount-in-tests' in volume and volume['mount-in-tests']['image-name'] == self.image_name:
                    host_path = str(mounted_project_dir / volume['host-path'])
                    container_path = volume['mount-in-tests']['path']
                    yield from ['-v', '{}:{}:rw'.format(host_path, container_path)]

    def run_default(self):
        try:
            sh.docker.run.bake(
                rm=True,
                _out=sys.stdout.buffer,
                _err=sys.stdout.buffer,
            )(
                *self.volumes,
                self.image,
                'fix_code_style',
            )
        except sh.ErrorReturnCode_127:
            instruction = 'You should implement `fix_code_style` command in the docker image!'
            raise NotImplementedError(instruction)
