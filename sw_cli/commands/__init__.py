import pathlib

from sw_cli import settings
from sw_cli.commands import custom_script
from . import bash_completion
from . import debug
from . import devel
from . import fix_code_style
from . import global_commands
from . import help
from . import init
from . import jenkins
from . import test


class CommandDeclaration:
    def __init__(self, name, source, kwargs=None):
        self.name = name
        self.source = source
        self.kwargs = kwargs or {}


commands = [
    CommandDeclaration('help', help.HelpCommand),
    CommandDeclaration('init', init.InitCommand),
    CommandDeclaration('install_bash_completion', bash_completion.InstallCompletion),
    CommandDeclaration('bash_completion', bash_completion.RunCompletion),
    CommandDeclaration('jenkins_init', jenkins.JenkinsInitCommand),
    CommandDeclaration('jenkins_build', jenkins.JenkinsBuildCommand),
    CommandDeclaration('jenkins_reconfig', jenkins.JenkinsReconfigCommand),
    CommandDeclaration('jenkins_info', jenkins.JenkinsInfoCommand),
    CommandDeclaration('variables', debug.DebugCommand),
    CommandDeclaration('build', devel.BuildCommand),
    CommandDeclaration('test', test.TestCommand),
    CommandDeclaration('update_requirements', devel.UpdateRequirementsCommand),
    CommandDeclaration('push', devel.PushCommand),
    CommandDeclaration('deploy', devel.DeployCommand),
    CommandDeclaration('setup', global_commands.SetupCommand),
    CommandDeclaration('install_global_secrets', global_commands.InstallGlobalSecretsCommand),
    CommandDeclaration('fix_code_style', fix_code_style.FixCodeStyle),
]


def get_all_commands():
    cmds = commands.copy()

    def cmd_exists(name):
        return any(cmd.name == name for cmd in cmds)

    scripts_dir = pathlib.Path(settings.DEFAULT_SWCLI_SCRIPTS_DIR)
    if scripts_dir.exists():
        scripts_dir = scripts_dir.resolve()
        for filepath in scripts_dir.glob("*"):
            if filepath.is_file() and not cmd_exists(filepath.name):
                cmds.append(CommandDeclaration(filepath.name, custom_script.CustomScriptCommand,
                                               kwargs={'script_name': filepath}))
    return cmds
