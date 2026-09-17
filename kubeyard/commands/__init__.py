from kubeyard.commands.bash_completion import InstallCompletion
from kubeyard.commands.build import BuildCommand
from kubeyard.commands.custom_script import CustomScriptCommand
from kubeyard.commands.debug import DebugCommand
from kubeyard.commands.deploy import DeployCommand
from kubeyard.commands.fix_code_style import FixCodeStyleCommand
from kubeyard.commands.global_commands import InstallGlobalSecretsCommand
from kubeyard.commands.global_commands import SetupCommand
from kubeyard.commands.init import InitCommand
from kubeyard.commands.push import PushCommand
from kubeyard.commands.seed import SeedCommand
from kubeyard.commands.shell import ShellCommand
from kubeyard.commands.test import TestCommand
from kubeyard.commands.undeploy import UndeployCommand
from kubeyard.commands.update_requirements import UpdateRequirementsCommand
from kubeyard.commands.workspace import CreateWorkspaceCommand
from kubeyard.commands.workspace import DestroyWorkspaceCommand
from kubeyard.commands.workspace import ListWorkspacesCommand
from kubeyard.commands.workspace import ShowWorkspaceCommand
from kubeyard.commands.workspace import SyncWorkspaceCommand

__all__ = [
    InstallCompletion,
    CustomScriptCommand,
    DebugCommand,
    BuildCommand,
    DeployCommand,
    PushCommand,
    SeedCommand,
    UpdateRequirementsCommand,
    FixCodeStyleCommand,
    InstallGlobalSecretsCommand,
    SetupCommand,
    InitCommand,
    TestCommand,
    ShellCommand,
    UndeployCommand,
    CreateWorkspaceCommand,
    DestroyWorkspaceCommand,
    ListWorkspacesCommand,
    ShowWorkspaceCommand,
    SyncWorkspaceCommand,
]
