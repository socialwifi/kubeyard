import os

import sh
from cached_property import cached_property

from sw_cli import base_command
from sw_cli.base_command import CommandException

DOCKER_ENV_KEYS = ['DOCKER_TLS_VERIFY', 'DOCKER_HOST', 'DOCKER_CERT_PATH', 'DOCKER_API_VERSION']


class DevelCommand(base_command.BaseCommand):

    def __init__(self):
        super(DevelCommand, self).__init__()
        self._prepare_minikube()

    def build(self):
        self._run_script('build')

    def test(self):
        self._run_script('test')

    def deploy(self):
        self._run_script('deploy')

    @cached_property
    def docker_env(self):
        variables = map(lambda x: '$' + x, DOCKER_ENV_KEYS)
        result = sh.bash('-c', 'eval $(minikube docker-env); echo "%s"' % '|'.join(variables))
        values = result.strip("\n").split('|')
        return dict(zip(DOCKER_ENV_KEYS, values))

    def _prepare_minikube(self):
        status = sh.minikube('status')
        if status.strip().lower() == 'stopped':
            print("Starting minikube...")
            sh.minikube('start')
        self.context.update(self.docker_env)

    def _run_script(self, script_name):
        filepath = self.project_dir / self.context.get('SWCLI_DEVEL_%s_SCRIPT_PATH' % script_name.upper())
        if not filepath.exists():
            raise CommandException("Could not execute %s command, file doesn't exist: %s" % (script_name, filepath))
        env = os.environ.copy()
        env.update(self.context)
        script = sh.Command(str(filepath))
        for line in script(_env=env, _iter=True):
            print(line)


def build():
    print("Starting command build")
    cmd = DevelCommand()
    cmd.build()
    print("Done.")


def test():
    print("Starting command test")
    cmd = DevelCommand()
    cmd.test()
    print("Done.")


def deploy():
    print("Starting command test")
    cmd = DevelCommand()
    cmd.deploy()
    print("Done.")
