import pathlib

from sw_cli import settings
from sw_cli.commands import custom_script


class CommandDeclaration:
    def __init__(self, name, source, kwargs=None):
        self.name = name
        self.source = source
        self.kwargs = kwargs or {}


def get_all_commands():
    cmds = []

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
