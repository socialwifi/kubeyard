from sw_cli.commands.bash_completion import InstallCompletion
from sw_cli.commands.custom_script import CustomScriptCommand
from sw_cli.commands.debug import DebugCommand
from sw_cli.commands.build import BuildCommand
from sw_cli.commands.deploy import DeployCommand
from sw_cli.commands.shell import ShellCommand
from sw_cli.commands.push import PushCommand
from sw_cli.commands.update_requirements import UpdateRequirementsCommand
from sw_cli.commands.fix_code_style import FixCodeStyleCommand
from sw_cli.commands.global_commands import InstallGlobalSecretsCommand
from sw_cli.commands.global_commands import SetupCommand
from sw_cli.commands.init import InitCommand
from sw_cli.commands.jenkins import JenkinsBuildCommand
from sw_cli.commands.jenkins import JenkinsInfoCommand
from sw_cli.commands.jenkins import JenkinsInitCommand
from sw_cli.commands.jenkins import JenkinsReconfigCommand
from sw_cli.commands.test import TestCommand

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
