import sh

from cached_property import cached_property

from sw_cli.base_command import CommandException
from sw_cli.commands.devel import BaseDevelCommand


class ShellCommand(BaseDevelCommand):
    """
    Command allows you to exec into container.
    """
    custom_script_name = 'shell'
    context_vars = ['pod', 'shell']

    def __init__(self, *, shell, pod, container, **kwargs):
        super().__init__(**kwargs)
        self.shell = shell
        self.pod = pod
        self.container = container

    def run_default(self):
        try:
            sh.kubectl.exec(
                "-it",
                self.pod_name,
                "-c", self.container_name,
                self.shell,
                _fg=True,
            )
        except sh.ErrorReturnCode_130:
            # Command exited using Ctrl+D or Ctrl+C
            pass

    @cached_property
    def pod_name(self) -> str:
        if self.pod:
            return self.pod
        else:
            for pod in sh.kubectl.get.pods(_iter='out'):
                if self.image_name in pod:
                    return pod.split()[0]
        raise CommandException("Container not found, please specify container or fix project setup.")

    @cached_property
    def container_name(self) -> str:
        if self.container:
            return self.container
        else:
            return self.image_name
