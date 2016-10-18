import os

import sh
import sys

from cached_property import cached_property

from sw_cli import base_command


class CustomScriptException(Exception):
    pass


class CustomScriptCommand(base_command.BaseCommand):
    def __init__(self, script_name):
        super().__init__()
        self.script_name = script_name

    @cached_property
    def options(self):
        parser = self.get_parser()
        return parser.parse_known_args()[0]

    def run(self):
        print("Starting command %s" % self.script_name)
        try:
            CustomScriptRunner(self.project_dir, self.context).run(self.script_name)
        except CustomScriptException as e:
            raise base_command.CommandException(*e.args)
        else:
            print("Done.")


class CustomScriptRunner:
    def __init__(self, project_dir, context):
        self.project_dir = project_dir
        self.context = context

    def run(self, script_name):
        filepath = self.project_dir / self.context.get('SWCLI_SCRIPTS_DIR') / script_name
        if not filepath.exists():
            raise CustomScriptException(
                "Could not execute %s command, script doesn't exist: %s" % (script_name, filepath))
        if not os.access(str(filepath), os.X_OK):
            raise PermissionError(
                "Could not execute %s command, script exists but is not executable: %s" % (script_name, filepath))
        env = os.environ.copy()
        env.update(self.context)
        script = sh.Command(str(filepath))
        for line in script(*sys.argv[2:], _env=env, _iter=True):
            print(line)
