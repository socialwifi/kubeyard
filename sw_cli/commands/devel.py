import collections
import contextlib

import kubepy.appliers
import kubepy.base_commands
import os
import sh
import time
from cached_property import cached_property

from sw_cli import base_command
from sw_cli import kubernetes
from sw_cli import minikube
from sw_cli import settings
from sw_cli.commands import custom_script


class BaseDevelCommand(base_command.BaseCommand):
    docker_repository = 'docker.socialwifi.com'

    def __init__(self):
        super().__init__()
        if self.context['SWCLI_MODE'] == 'development':
            self._prepare_minikube()

    def run(self):
        if self.options.default:
            self.run_default()
        else:
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
        parser.add_option(
            '--default', dest='default', action='store_true', default=False,
            help='Don\'t try to execute custom script. Useful when you need original behaviour in overridden method')
        return parser

    def docker(self, *args, **kwargs):
        return sh.docker(*args, _env=self.sh_env, **kwargs)

    @property
    def image(self):
        return '{}/{}:{}'.format(self.docker_repository, self.context["DOCKER_IMAGE_NAME"], self.tag)

    @property
    def latest_image(self):

        return '{}/{}:latest'.format(self.docker_repository, self.context["DOCKER_IMAGE_NAME"])

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

    @cached_property
    def sh_env(self):
        env = os.environ.copy()
        env.update(self.context)
        return env


class BuildCommand(BaseDevelCommand):
    custom_script_name = 'build'

    def run_default(self):
        docker_dir = "{0}/docker".format(self.project_dir)
        for line in sh.docker('build', '-t', self.image, docker_dir, _iter=True, _env=self.sh_env):
            print(line)


class TestCommand(BaseDevelCommand):
    custom_script_name = 'test'

    def run_default(self):
        for line in sh.docker('run', '--rm', self.image, 'run_tests', _iter=True, _env=self.sh_env):
            print(line)


class PushCommand(BaseDevelCommand):
    custom_script_name = 'push'

    def run_default(self):
        for line in sh.docker('push', self.image, _iter=True, _env=self.sh_env):
            print(line)
        for line in sh.docker('tag', self.image, self.latest_image, _iter=True, _env=self.sh_env):
            print(line)
        for line in sh.docker('push', self.latest_image, _iter=True, _env=self.sh_env):
            print(line)


KubepyOptions = collections.namedtuple('KubepyOptions', ['build_tag'])


class DeployCommand(BaseDevelCommand):
    custom_script_name = 'deploy'

    def run_default(self):
        kubernetes_dir = self.project_dir / settings.DEFAULT_KUBERNETES_DEPLOY_DIR
        options = KubepyOptions(self.tag)
        kubernetes.install_secrets(self.context)
        kubepy.appliers.DirectoryApplier(kubernetes_dir, options).apply_all()


class SetupDevDbCommand(BaseDevelCommand):
    custom_script_name = 'setup_dev_db'
    postgres_started_log = 'PostgreSQL init process complete; ready for start up.'

    def run_default(self):
        postgres_name = self.context['DEV_POSTGRES_NAME']
        self.ensure_postgres_running(postgres_name)

    def ensure_postgres_running(self, postgres_name):
        try:
            postgres_status = str(self.docker('inspect', '--format={{.State.Status}}', postgres_name)).strip()
        except sh.ErrorReturnCode:
            postgres_status = 'error'
        if postgres_status != 'running':
            with contextlib.suppress(sh.ErrorReturnCode):
                self.docker('rm', '-fv', postgres_name)
            self.run_fresh_postgres(postgres_name)

    def run_fresh_postgres(self, postgres_name):
        print('running postgres')
        self.docker('run', '-d', '--name={}'.format(postgres_name), '-p', '172.17.0.1:35432:5432', 'postgres:9.6.0')
        for log in self.docker('logs', '-f', postgres_name, _iter=True):
            print(log.strip())
            if self.postgres_started_log in log:
                break


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


def push():
    print("Starting command push")
    cmd = PushCommand()
    cmd.run()
    print("Done.")


def deploy():
    print("Starting command deploy")
    cmd = DeployCommand()
    cmd.run()
    print("Done.")


def setup_dev_db():
    print("Setting up dev db")
    cmd = SetupDevDbCommand()
    cmd.run()
    print("Done.")
