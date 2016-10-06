import kubepy.appliers
import kubepy.base_commands
import sh

from sw_cli import base_command
from sw_cli import minikube
from sw_cli import settings
from sw_cli.commands import custom_script


class BaseDevelCommand(base_command.BaseCommand):
    def __init__(self):
        super().__init__()
        if self.context['SWCLI_MODE'] == 'development':
            self._prepare_minikube()

    def run(self):
        try:
            custom_script.CustomScriptRunner(self.project_dir, self.context).run(self.custom_script_name)
        except custom_script.CustomScriptException:
            self.run_default()

    def _prepare_minikube(self):
        minikube.ensure_minikube_started()
        self.context.update(minikube.docker_env())

    def run_default(self):
        raise NotImplementedError

    @property
    def custom_script_name(self):
        raise NotImplementedError


class BuildCommand(BaseDevelCommand):
    custom_script_name = 'build'

    def run_default(self):
        docker_image = self.context["DOCKER_IMAGE_NAME"]
        docker_dir = "{0}/docker".format(self.project_dir)
        for line in sh.docker('build', '-t', docker_image, docker_dir, _iter=True):
            print(line)


class TestCommand(BaseDevelCommand):
    custom_script_name = 'test'

    def run_default(self):
        docker_image = self.context["DOCKER_IMAGE_NAME"]
        for line in sh.docker('run', '--rm', docker_image, 'run_tests', _iter=True):
            print(line)


class DeployCommand(BaseDevelCommand):
    custom_script_name = 'deploy'

    def run_default(self):
        kubernetes_dir = self.project_dir / settings.DEFAULT_KUBERNETES_DIR_PATH
        kubepy.appliers.DirectoryApplier(kubernetes_dir, self.options).apply_all()

    def get_parser(self):
        parser = super().get_parser()
        kubepy.base_commands.add_container_options(parser)
        return parser


def build():
    print("Starting command build")
    cmd = BuildCommand()
    cmd.run()
    print("Done.")


def test():
    print("Starting command test")
    cmd = TestCommand()
    cmd.run()
    print("Done.")


def deploy():
    print("Starting command test")
    cmd = DeployCommand()
    cmd.run()
    print("Done.")
