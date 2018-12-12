import logging
import os

from kubeyard import base_command

logger = logging.getLogger(__name__)


class CustomScriptCommand(base_command.InitialisedRepositoryCommand):
    """
    * Custom script defined in ./scripts/ directory. Running it with kubeyard add current context to environment.
    """

    def __init__(self, script_name, custom_script_args, **kwargs):
        super().__init__(**kwargs)
        self.script_name = script_name
        self.custom_script_args = list(custom_script_args)

    def run(self):
        super().run()
        logger.info('Running custom script command "{}"...'.format(self.script_name))
        CustomScriptRunner(self.project_dir, self.context).run(self.script_name, self.custom_script_args)


class CustomScriptRunner:
    def __init__(self, project_dir, context):
        self.project_dir = project_dir
        self.context = context

    def run(self, script_name, args):
        filepath = self.scripts_dir_path / script_name
        env = os.environ.copy()
        env.update(self.context.as_environment())
        os.execvpe(file=str(filepath), args=[str(filepath)] + args, env=env)

    def exists(self, script_name):
        return (self.scripts_dir_path / script_name).exists()

    @property
    def scripts_dir_path(self):
        return self.project_dir / self.context.get('KUBEYARD_SCRIPTS_DIR')
