import logging

import sh

from cached_property import cached_property

from kubeyard.base_command import CommandException
from kubeyard.commands.devel import BaseDevelCommand

logger = logging.getLogger(__name__)


class ShellCommand(BaseDevelCommand):
    """
    Command allows you to exec into container.
    """
    custom_script_name = 'shell'
    context_vars = ['pod', 'shell']

    def __init__(self, *, shell, pod, container, root, **kwargs):
        super().__init__(**kwargs)
        self.shell = shell
        self.pod = pod
        self.container = container
        self.root = root

    def run_default(self):
        try:
            sh.kubectl.exec(
                "-it",
                self.pod_name,
                "-c", self.container_name,
                '--',
                self.shell,
                "-c", self.before_command,
                _fg=True,
            )
        except sh.ErrorReturnCode_130:
            # Command exited using Ctrl+D or Ctrl+C
            pass
        finally:
            if self.after_command:
                sh.kubectl.exec(
                    self.pod_name,
                    "-c", self.container_name,
                    "--",
                    self.shell,
                    "-c", self.after_command,
                )

    @cached_property
    def pod_name(self) -> str:
        if self.pod:
            all_pods = sh.kubectl.get.pods('-o', 'jsonpath={.items[*].metadata.name}').split()
            # Exact match
            if self.pod in all_pods:
                return self.pod
            # Starting-with match
            pods = [pod for pod in all_pods if pod.startswith(self.pod)]
            pods.sort(key=len)
            if len(pods) == 0:
                raise CommandException(f"Not found pod equal or starting with '{self.pod}'")
            if len(pods) > 1:
                logger.warning(f"Found more than one pod. Using '{pods[0]}'")
            return pods[0]
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

    @cached_property
    def username(self) -> str:
        return str(sh.whoami()).strip()

    @property
    def before_command(self):
        if self.root:
            return self.shell
        return (
            'groupadd -f -g {gid} {username}; '
            'adduser -q --gecos "" --disabled-password --uid {uid} --gid {gid} {username}; '
            'su {username}; '
        ).format(
            gid=self.gid,
            uid=self.uid,
            username=self.username,
        )

    @property
    def after_command(self) -> str:
        if self.root:
            return ""
        else:
            return "userdel --remove {username}; ".format(username=self.username)
