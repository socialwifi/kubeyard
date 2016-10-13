import pathlib
from collections import namedtuple

from sw_cli import settings
from sw_cli.commands import custom_script
from . import bash_completion
from . import debug
from . import devel
from . import global_commands
from . import init_repo
from . import jenkins


CommandDeclaration = namedtuple('CommandDeclaration', ['name', 'source'])

commands = [
    CommandDeclaration('init_repo', init_repo.run),
    CommandDeclaration('install_bash_completion', bash_completion.install),
    CommandDeclaration('bash_completion', bash_completion.run),
    CommandDeclaration('jenkins_init', jenkins.init),
    CommandDeclaration('jenkins_build', jenkins.build),
    CommandDeclaration('jenkins_reconfig', jenkins.reconfig),
    CommandDeclaration('jenkins_info', jenkins.info),
    CommandDeclaration('variables', debug.variables),
    CommandDeclaration('build', devel.build),
    CommandDeclaration('test', devel.test),
    CommandDeclaration('push', devel.push),
    CommandDeclaration('deploy', devel.deploy),
    CommandDeclaration('setup_dev_db', devel.setup_dev_db),
    CommandDeclaration('setup', global_commands.setup),
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
                command = custom_script.CustomScriptCommand(filepath)
                cmds.append(CommandDeclaration(filepath.name, command.run))

    return cmds
