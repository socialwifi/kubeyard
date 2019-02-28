import abc
import logging
import pathlib

from cached_property import cached_property

from kubeyard import context_factories
from kubeyard import settings

logger = logging.getLogger(__name__)


class CommandException(Exception):
    pass


class BaseCommand:
    @abc.abstractmethod
    def run(self):
        raise NotImplementedError


class ContextFromClassPropertiesBuilderMetaclass(type):
    def __new__(mcs, name, bases, dct):
        dct['context_vars'] = dct.get('context_vars', [])
        for base in bases:
            if hasattr(base, 'context_vars'):
                dct['context_vars'] += base.context_vars
        obj = super().__new__(mcs, name, bases, dct)
        return obj


class InitialisedRepositoryCommand(BaseCommand, metaclass=ContextFromClassPropertiesBuilderMetaclass):
    context_vars = ['directory']

    def __init__(self, *, directory, log_level):
        super().__init__()
        self.directory = directory
        self._log_level = log_level

    def run(self):
        self.set_log_level()

    def set_log_level(self):
        logging.getLogger('kubeyard').setLevel(self.log_level)

    @property
    def log_level(self):
        return self._log_level or self.context.get('KUBEYARD_LOG_LEVEL', settings.DEFAULT_KUBEYARD_LOG_LEVEL)

    @cached_property
    def context(self):
        try:
            return context_factories.InitialisedRepoContextFactory(self.project_dir).get()
        except FileNotFoundError:
            logger.error("Invalid project root directory: {}. Exiting.".format(self.project_dir))
            exit(1)

    @cached_property
    def project_dir(self):
        return pathlib.Path(self.directory)

    @cached_property
    def custom_command_context(self):
        """
        If you want to pass any property of class, you should OVERRIDE `context_vars` class property.
        """
        context = context_factories.Context()
        context.update(self.context)
        context.update(context_factories.Context(
            {field.upper(): getattr(self, field) for field in self.context_vars},
        ))
        return context
