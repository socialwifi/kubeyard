import logging
import os

from cached_property import cached_property

from sw_cli import base_command


logger = logging.getLogger(__name__)


class CustomScriptException(Exception):
    pass


class CustomScriptCommand(base_command.InitialisedRepositoryCommand):
    """
    Custom script defined in ./scripts/ directory. Running it with sw-cli add current context to environment.
    """
    def __init__(self, *args, script_name):
        super().__init__(*args)
        self.script_name = script_name

    @cached_property
    def options(self):
        parser = self.get_parser()
        return parser.parse_known_args()[0]

    def run(self):
        super().run()
        logger.info('Running custom script command "{}"...'.format(self.script_name))
        try:
            CustomScriptRunner(self.project_dir, self.context).run(self.script_name, self.args)
        except CustomScriptException as e:
            raise base_command.CommandException(*e.args)
        else:
            logger.info("Done")


class CustomScriptRunner:
    def __init__(self, project_dir, context):
        self.project_dir = project_dir
        self.context = context

    def run(self, script_name, args):
        filepath = self.project_dir / self.context.get('SWCLI_SCRIPTS_DIR') / script_name
        if not filepath.exists():
            raise CustomScriptException(
                "Could not execute %s command, script doesn't exist: %s" % (script_name, filepath))
        if not os.access(str(filepath), os.X_OK):
            raise PermissionError(
                "Could not execute %s command, script exists but is not executable: %s" % (script_name, filepath))
        env = os.environ.copy()
        env.update(self.context.as_environment())
        os.execvpe(file=str(filepath), args=[str(filepath)] + args, env=env)
