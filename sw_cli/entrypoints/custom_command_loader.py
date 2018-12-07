import os
import pathlib

import click

from cached_property import cached_property

from sw_cli import settings
from sw_cli.commands import CustomScriptCommand


class CustomCommandsLoader(click.MultiCommand):
    scripts_dir = pathlib.Path(settings.DEFAULT_SWCLI_SCRIPTS_DIR)

    def __init__(self, main_cli: list, **attrs):
        """
        :param main_cli: Is required to pass main CLI to not override methods from CLI on current level.
        """
        super().__init__(**attrs)
        self.main_cli = main_cli

    @cached_property
    def custom_scripts(self):
        cmds = {}
        if self.scripts_dir.exists():
            scripts_dir = self.scripts_dir.resolve()
            for filepath in scripts_dir.glob("*"):
                if filepath.is_file() and self.is_executable(filepath):
                    cmds[filepath.name] = filepath
        return cmds

    @staticmethod
    def is_executable(filepath: pathlib.Path) -> bool:
        return os.access(filepath, os.X_OK)

    def list_commands(self, ctx):
        """Do not override commands from main CLI"""
        return [cs for cs in self.custom_scripts.keys() if cs not in self.main_cli.list_commands(ctx)]

    def get_command(self, ctx, cmd_name):
        from sw_cli.entrypoints.sw_cli import apply_common_options
        from sw_cli.entrypoints.sw_cli import initialized_repository_options

        @click.command(
            name=cmd_name,
            help=CustomScriptCommand.__doc__,
            context_settings=dict(
                ignore_unknown_options=True,
            ),
        )
        @apply_common_options(initialized_repository_options)
        @click.argument("custom_script_args", nargs=-1, type=click.UNPROCESSED)
        def _custom_script_command(**kwargs):
            CustomScriptCommand(script_name=self.custom_scripts[cmd_name], **kwargs).run()

        return _custom_script_command
