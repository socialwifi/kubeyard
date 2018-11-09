import logging
import os

from cached_property import cached_property

from sw_cli import base_command

logger = logging.getLogger(__name__)


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
        CustomScriptRunner(self.project_dir, self.context).run(self.script_name, self.args)


class CustomScriptRunner:
    def __init__(self, project_dir, context):
        self.project_dir = project_dir
        self.context = context

    def run(self, script_name, args):
        filepath = self.scripts_dir_path / script_name
        if not self.is_executable(script_name):
            raise PermissionError("Could not execute %s command, script exists but is not executable: %s"
                                  % (script_name, filepath))
        env = os.environ.copy()
        env.update(self.context.as_environment())
        os.execvpe(file=str(filepath), args=[str(filepath)] + args, env=env)

    def exists(self, script_name):
        return (self.scripts_dir_path / script_name).exists()

    def is_executable(self, script_name):
        filepath = self.scripts_dir_path / script_name
        return os.access(str(filepath), os.X_OK)

    @property
    def scripts_dir_path(self):
        return self.project_dir / self.context.get('SWCLI_SCRIPTS_DIR')
