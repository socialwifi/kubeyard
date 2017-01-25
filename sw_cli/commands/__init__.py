import pathlib
from collections import namedtuple

from sw_cli import settings
from sw_cli.commands import custom_script
from . import bash_completion
from . import debug
from . import devel
from . import global_commands
from . import init
from . import jenkins


CommandDeclaration = namedtuple('CommandDeclaration', ['name', 'source'])

commands = [
    CommandDeclaration('init', init.run),
    CommandDeclaration('install_bash_completion', bash_completion.install),
    CommandDeclaration('bash_completion', bash_completion.run),
    CommandDeclaration('jenkins_init', jenkins.init),
    CommandDeclaration('jenkins_build', jenkins.build),
    CommandDeclaration('jenkins_reconfig', jenkins.reconfig),
    CommandDeclaration('jenkins_info', jenkins.info),
    CommandDeclaration('variables', debug.variables),
    CommandDeclaration('build', devel.build),
    CommandDeclaration('test', devel.test),
    CommandDeclaration('update_requirements', devel.requirements),
    CommandDeclaration('push', devel.push),
    CommandDeclaration('deploy', devel.deploy),
    CommandDeclaration('setup_dev_db', devel.setup_dev_db),
    CommandDeclaration('setup_dev_elastic', devel.setup_dev_elastic),
    CommandDeclaration('setup_pubsub_emulator', devel.setup_pubsub_emulator),
    CommandDeclaration('setup_dev_redis', devel.setup_dev_redis),
    CommandDeclaration('setup', global_commands.setup),
    CommandDeclaration('install_global_secrets', global_commands.install_global_secrets),
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
                command = custom_script.custom_script_factory(filepath)
                cmds.append(CommandDeclaration(filepath.name, command))

    return cmds
