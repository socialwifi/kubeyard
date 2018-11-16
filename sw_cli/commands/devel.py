import abc
import io
import logging
import os
import signal
import sys

from contextlib import contextmanager

import sh

from cached_property import cached_property

from sw_cli import base_command
from sw_cli import minikube
from sw_cli import settings
from sw_cli.commands import custom_script

logger = logging.getLogger(__name__)

MAX_JOB_RETRIES = 2


class BaseDevelCommand(base_command.InitialisedRepositoryCommand):
    context_vars = ['image_name', 'tag']

    def __init__(self, *, use_default_implementation, image_name, tag, **kwargs):
        super().__init__(**kwargs)
        self._image_name = image_name
        self._tag = tag
        self.use_default_implementation = use_default_implementation
        if self.is_development:
            self.cluster = self._prepare_cluster(self.context)
            self.context.update(self.cluster.docker_env())
        self.docker_runner = DockerRunner(self.context)

    @staticmethod
    def _prepare_cluster(context):
        logger.info('Checking if cluster is running and configured...')
        cluster = minikube.ClusterFactory().get(context)
        cluster.ensure_started()
        logger.info('Cluster is ready')
        return cluster

    @property
    def args(self) -> list:
        return []

    def run(self):
        super().run()
        custom_script_runner = custom_script.CustomScriptRunner(self.project_dir, self.custom_command_context)
        custom_script_exists = custom_script_runner.exists(self.custom_script_name)
        if self.use_default_implementation or not custom_script_exists:
            self.run_default()
        else:
            custom_script_runner.run(self.custom_script_name, self.args)

    def docker(self, *args, **kwargs):
        return self.docker_runner.run(*args, **kwargs)

    def docker_with_output(self, *args, **kwargs):
        return self.docker_runner.run_with_output(*args, **kwargs)

    @property
    def image(self):
        return '{}/{}:{}'.format(self.docker_repository, self.image_name, self.tag)

    @property
    def latest_image(self):
        return '{}/{}:latest'.format(self.docker_repository, self.image_name)

    @property
    def docker_repository(self):
        return self.context.get("DOCKER_REGISTRY_NAME") or settings.DEFAULT_DOCKER_REGISTRY_NAME

    @property
    def image_name(self):
        return self._image_name or self.context["DOCKER_IMAGE_NAME"]

    @property
    def tag(self):
        return self._tag or self.default_tag

    @property
    def default_tag(self):
        if self.is_development:
            return 'dev'
        else:
            return 'latest'

    @property
    def is_development(self):
        return self.context['SWCLI_MODE'] == 'development'

    def run_default(self):
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def custom_script_name(self):
        raise NotImplementedError


class UpdateRequirementsCommand(BaseDevelCommand):
    """
    Updates docker/requirements/python.txt file based on docker/source/base_requirements.txt.
    In container it creates virtualenv and runs:

        pip install -r docker/source/base_requirements.txt && pip freeze > docker/source/base_requirements.txt

    Can be overridden in <project_dir>/sripts/update_requirements.

    If sw-cli is set up in development mode it uses minikube as docker host.
    """
    custom_script_name = 'update_requirements'
    context_vars = ['use_legacy_pip']

    def __init__(self, use_legacy_pip=False, **kwargs):
        super().__init__(**kwargs)
        self.use_legacy_pip = use_legacy_pip

    def run_default(self):
        logger.info('Updating requirements for "{}"...'.format(self.image))
        if self.use_legacy_pip is True:
            os.system(self.legacy_pip_freeze_command)
        else:
            with open("docker/requirements/python.txt", "w") as output_file:
                output_file.write(self.get_pip_freeze_output())
        logger.info('Requirements updated and saved to "docker/requirements/python.txt"')

    @property
    def legacy_pip_freeze_command(self):
        return ('(cat docker/source/base_requirements.txt | docker run --rm -i python:3.6.0'
                ' bash -c "'
                'pip install --upgrade setuptools==34.3.0 > /dev/stderr ; '
                'pip install -r /dev/stdin > /dev/stderr ; '
                'pip freeze")'
                ' > docker/requirements.txt')

    def get_pip_freeze_output(self):
        output = io.StringIO()
        input = sh.cat("docker/source/base_requirements.txt")
        self.docker('run', '--rm', '-i',
                    '-e', 'CUSTOM_COMPILE_COMMAND="sw-cli update_requirements"',
                    self.image, 'freeze_requirements',
                    _in=input, _out=output, _err=sys.stdout.buffer)
        return output.getvalue()


class DockerRunner:
    def __init__(self, context):
        self.context = context

    def run(self, *args, **kwargs):
        if self.run_can_be_waited(*args, **kwargs):
            process: sh.RunningCommand = sh.docker(*args, _env=self.sh_env, _bg=True, **kwargs)
            try:
                process.wait()
            except KeyboardInterrupt as e:
                logger.info("Stopping running command...")
                process.signal(signal.SIGINT)
                raise e
        else:
            process: sh.RunningCommand = sh.docker(*args, _env=self.sh_env, **kwargs)
        return process

    def run_can_be_waited(self, *args, _piped=False, _iter=False, _iter_noblock=False, **kwargs) -> bool:
        """Check special cases when sh require to not use .wait() method"""
        return not any((_piped, _iter, _iter_noblock))

    def run_with_output(self, *args, **kwargs):
        return self.run(*args, _out=sys.stdout.buffer, _err=sys.stdout.buffer, **kwargs)

    @cached_property
    def sh_env(self):
        env = os.environ.copy()
        env.update(self.context.as_environment())
        return env

    @contextmanager
    def temporary_volume(self):
        volume_name = self.run('volume', 'create').strip()
        logger.debug('volume_name: {}'.format(volume_name))
        yield volume_name
        self.run('volume', 'remove', volume_name)
