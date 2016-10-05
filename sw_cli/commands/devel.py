import os

import sh

from sw_cli import base_command
from sw_cli import minikube


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

    def _prepare_minikube(self):
        minikube.ensure_minikube_started()
        self.context.update(minikube.docker_env())

    def _run_script(self, script_name):
        filepath = self.project_dir / self.context.get('SWCLI_DEVEL_%s_SCRIPT_PATH' % script_name.upper())
        if not filepath.exists():
            raise base_command.CommandException("Could not execute %s command, file doesn't exist: %s" % (script_name, filepath))
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
