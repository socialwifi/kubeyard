from kubeyard.commands.bash_completion import InstallCompletion
from kubeyard.commands.custom_script import CustomScriptCommand
from kubeyard.commands.debug import DebugCommand
from kubeyard.commands.build import BuildCommand
from kubeyard.commands.deploy import DeployCommand
from kubeyard.commands.shell import ShellCommand
from kubeyard.commands.push import PushCommand
from kubeyard.commands.update_requirements import UpdateRequirementsCommand
from kubeyard.commands.fix_code_style import FixCodeStyleCommand
from kubeyard.commands.global_commands import InstallGlobalSecretsCommand
from kubeyard.commands.global_commands import SetupCommand
from kubeyard.commands.init import InitCommand
from kubeyard.commands.jenkins import JenkinsBuildCommand
from kubeyard.commands.jenkins import JenkinsInfoCommand
from kubeyard.commands.jenkins import JenkinsInitCommand
from kubeyard.commands.jenkins import JenkinsReconfigCommand
from kubeyard.commands.test import TestCommand

__all__ = [
    InstallCompletion,
    CustomScriptCommand,
    DebugCommand,
    BuildCommand,
    DeployCommand,
    PushCommand,
    UpdateRequirementsCommand,
    FixCodeStyleCommand,
    InstallGlobalSecretsCommand,
    SetupCommand,
    InitCommand,
    JenkinsBuildCommand,
    JenkinsInfoCommand,
    JenkinsInitCommand,
    JenkinsReconfigCommand,
    TestCommand,
    ShellCommand,
]
