import os

import sh

from sw_cli import minikube
from sw_cli import base_command
from sw_cli.commands import custom_script


class DevelCommand(custom_script.CustomScriptCommand):
    def __init__(self):
        super(DevelCommand, self).__init__()
        self._prepare_minikube()

    def build(self):
        try:
            self.run('build')
        except base_command.CommandException:
            main_directory = sh.bash('-c', 'echo $(pushd "$(dirname "${BASH_SOURCE[0]}")" > '
                                     '/dev/null; git rev-parse --show-toplevel; popd > /dev/null)').strip()
            docker_image = self.context["DOCKER_IMAGE"]
            docker_dir = "{0}/docker".format(main_directory)
            for line in sh.docker('build', '-t', docker_image, docker_dir, _iter=True):
                print(line)

    def test(self):
        self.run('test')

    def deploy(self):
        self.run('deploy')

    def _prepare_minikube(self):
        minikube.ensure_minikube_started()
        self.context.update(minikube.docker_env())


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
