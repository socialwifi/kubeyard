import abc
import logging
import pathlib
import random
import string

import kubeyard.files_generator

from kubeyard import base_command
from kubeyard import context_factories
from kubeyard import settings

logger = logging.getLogger(__name__)


class InitCommand(base_command.BaseCommand):
    """
    Initialises empty repository. Adds basic configuration and placeholders for source code and tests.
    It can be run only in git repository. It also adds missing files in not empty repositories.
    Most commands requires repository to have files structure as provisioned by this command.
    By default it uses python application template.
    """

    def __init__(self, *, directory, init_type: 'InitType'):
        self.directory = directory
        self.init_type = init_type

    def run(self):
        logger.info("Initialising repo...")
        project_dst = pathlib.Path(self.directory)
        context = context_factories.EmptyRepoContextFactory(self.directory, self.init_type.prompted_context).get()
        template_location = f'new_repositories/{self.init_type.name}'
        kubeyard.files_generator.copy_template(template_location, project_dst, context=context)


class InitType(metaclass=abc.ABCMeta):
    name: str = NotImplemented
    prompted_context: list = NotImplemented


class PythonPackageInitType(InitType):
    name = 'python'
    prompted_context = [
        context_factories.PromptedContext(
            'KUBE_SERVICE_NAME', 'service name', settings.DEFAULT_KUBE_SERVICE_NAME_PATTERN),
        context_factories.PromptedContext(
            'KUBE_SERVICE_PORT', 'service port', settings.DEFAULT_KUBE_SERVICE_PORT),
        context_factories.PromptedContext(
            'DOCKER_REGISTRY_NAME', 'docker registry name', settings.DEFAULT_DOCKER_REGISTRY_NAME),
    ]


class PythonDjangoInitType(InitType):
    name = 'django'
    prompted_context = [
        context_factories.PromptedContext(
            'KUBE_SERVICE_NAME', 'service name', settings.DEFAULT_KUBE_SERVICE_NAME_PATTERN),
        context_factories.PromptedContext(
            'KUBE_SERVICE_PORT', 'service port', settings.DEFAULT_KUBE_SERVICE_PORT),
        context_factories.PromptedContext(
            'DOCKER_REGISTRY_NAME', 'docker registry name', settings.DEFAULT_DOCKER_REGISTRY_NAME),
        context_factories.PromptedContext(
            'SECRET_KEY',
            'application secret key',
            ''.join(random.choices(string.ascii_letters + string.digits, k=50)),
        ),
    ]


class EmberInitType(InitType):
    name = 'ember'
    prompted_context = PythonPackageInitType.prompted_context + [
        context_factories.PromptedContext(
            'KUBE_LIVE_RELOAD_PORT', 'live reload development port', settings.DEFAULT_KUBE_LIVE_RELOAD_PORT),
        context_factories.PromptedContext(
            'DOCKER_REGISTRY_NAME', 'docker registry name', settings.DEFAULT_DOCKER_REGISTRY_NAME),
    ]


all_templates = [
    PythonPackageInitType,
    PythonDjangoInitType,
    EmberInitType,
]
