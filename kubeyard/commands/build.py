import logging
import shlex

from kubeyard.commands.devel import BaseDevelCommand

logger = logging.getLogger(__name__)


class BuildCommand(BaseDevelCommand):
    """
    Builds docker image required to run tests and deployment. Can be overridden in <project_dir>/sripts/build.
    If kubeyard is set up in development mode it uses minikube as docker host.
    """
    custom_script_name = 'build'
    context_vars = ['image_context', 'docker_args']

    def __init__(self, *, image_context, docker_args, **kwargs):
        super().__init__(**kwargs)
        self.image_context = image_context
        self.docker_args = docker_args or ''

    def run_default(self):
        image_context = self.image_context or "{0}/docker".format(self.project_dir)
        logger.info('Building image "{}"...'.format(self.image))
        self.docker_with_output('build', '-t', self.image, *shlex.split(self.docker_args),  image_context)
