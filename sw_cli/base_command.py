import abc
import logging
import pathlib

from cached_property import cached_property

from sw_cli import context_factories
from sw_cli import settings

logger = logging.getLogger(__name__)


class CommandException(Exception):
    pass


class BaseCommand(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def run(self):
        raise NotImplementedError


class InitialisedRepositoryCommand(BaseCommand, metaclass=abc.ABCMeta):
    def __init__(self, *, directory, log_level):
        super().__init__()
        self.directory = directory
        self._log_level = log_level

    def run(self):
        self.set_log_level()

    def set_log_level(self):
        logging.getLogger('sw_cli').setLevel(self.log_level)

    @property
    def log_level(self):
        return self._log_level or self.context.get('SWCLI_LOG_LEVEL', settings.DEFAULT_SWCLI_LOG_LEVEL)

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
