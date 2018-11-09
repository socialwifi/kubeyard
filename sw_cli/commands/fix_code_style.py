import logging
import sys
import typing

import sh

from sw_cli import base_command
from sw_cli.commands.devel import BaseDevelCommand

logger = logging.getLogger(__name__)


class FixCodeStyle(BaseDevelCommand):
    custom_script_name = 'fix_code_style'

    def __init__(self, *args):
        super().__init__(*args)

    @property
    def volumes(self) -> typing.Iterable[str]:
        if self.is_development:
            mounted_project_dir = self.cluster.get_mounted_project_dir(self.project_dir)
            for volume in self.context.get('DEV_MOUNTED_PATHS', []):
                if 'mount-in-tests' in volume and volume['mount-in-tests']['image-name'] == self.image_name:
                    host_path = str(mounted_project_dir / volume['host-path'])
                    container_path = volume['mount-in-tests']['path']
                    mount_mode = self.get_mount_mode(volume['mount-in-tests'])
                    yield from ['-v', '{}:{}:{}'.format(host_path, container_path, mount_mode)]

    def get_mount_mode(self, configuration):
        mount_mode = configuration.get('mount-mode', 'ro')
        if mount_mode not in {'ro', 'rw'}:
            raise base_command.CommandException('Volume "mount-mode" should be one of: "ro", "rw".')
        return mount_mode

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
