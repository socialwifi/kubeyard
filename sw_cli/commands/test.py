import logging

from sw_cli import base_command
from sw_cli.commands.devel import BaseDevelCommand

logger = logging.getLogger(__name__)


class TestCommand(BaseDevelCommand):
    """
    Runs tests in docker image built by build command. Can be overridden in <project_dir>/sripts/test.
    If sw-cli is set up in development mode it uses minikube as docker host and mounts volumes configured in
    dev_mounted_paths in config/sw_cli.yml if they have mount-in-test set.

    Example:
    dev_mounted_paths:
    - name: dev-volume
      host-path: docker/source
      mount-in-tests:
        path: /package
        image-name: sw-project
    """
    custom_script_name = 'test'

    def __init__(self, *args):
        super().__init__(*args)
        self.context['HOST_VOLUMES'] = ' '.join(self.volumes)

    def run_default(self):
        self.docker_with_output('run', '--rm', '--net=none', *self.volumes, self.image, 'run_tests')

    @property
    def volumes(self):
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
