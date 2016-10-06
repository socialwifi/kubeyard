import collections
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

    def get_parser(self):
        parser = super().get_parser()
        parser.add_option(
            '--tag', dest='tag', action='store', default=None, help='used image tag')
        return parser

    @property
    def image(self):
        return '{}:{}'. format(self.context["DOCKER_IMAGE_NAME"], self.tag)

    @property
    def tag(self):
        return self.options.tag or self.default_tag

    @property
    def default_tag(self):
        if self.context['SWCLI_MODE'] == 'development':
            return 'dev'
        else:
            return 'latest'

    def run_default(self):
        raise NotImplementedError

    @property
    def custom_script_name(self):
        raise NotImplementedError


class BuildCommand(BaseDevelCommand):
    custom_script_name = 'build'

    def run_default(self):
        docker_dir = "{0}/docker".format(self.project_dir)
        for line in sh.docker('build', '-t', self.image, docker_dir, _iter=True):
            print(line)


class TestCommand(BaseDevelCommand):
    custom_script_name = 'test'

    def run_default(self):
        for line in sh.docker('run', '--rm', self.image, 'run_tests', _iter=True):
            print(line)

KubepyOptions = collections.namedtuple('KubepyOptions', ['build_tag'])


class DeployCommand(BaseDevelCommand):
    custom_script_name = 'deploy'

    def run_default(self):
        kubernetes_dir = self.project_dir / settings.DEFAULT_KUBERNETES_DIR_PATH
        options = KubepyOptions(self.tag)
        kubepy.appliers.DirectoryApplier(kubernetes_dir, options).apply_all()


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
