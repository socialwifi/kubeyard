import collections
import logging
import pathlib

import git
import yaml

from cached_property import cached_property

from sw_cli import io_utils
from sw_cli import settings

logger = logging.getLogger(__name__)


class Context(dict):
    def as_environment(self):
        for key, value in self.items():
            if isinstance(value, str):
                yield key, value
            else:
                yield key, yaml.dump(value)


class GlobalContextFactory:
    def __init__(self):
        self.user_context_path = get_user_context_path()

    def get(self):
        context = Context()
        context.update(self.jenkins_info)
        context.update(self.base_user_context)
        context.update(self.user_context)
        return upper_keys(context)

    @cached_property
    def jenkins_info(self):
        return Context({
            'JENKINS_URL': settings.DEFAULT_JENKINS_URL,
            'JENKINS_EMAIL_RECIPIENTS': settings.DEFAULT_JENKINS_EMAIL_RECIPIENTS,
        })

    @cached_property
    def base_user_context(self):
        return Context({
            'KUBEYARD_USER_CONTEXT_FILEPATH': str(self.user_context_path),
            'KUBEYARD_MODE': 'production',
            'DEV_POSTGRES_NAME': settings.DEFAULT_DEV_POSTGRES_NAME,
            'DEV_PUBSUB_NAME': settings.DEFAULT_DEV_PUBSUB_NAME,
            'DEFAULT_DEV_ELASTIC_NAME': settings.DEFAULT_DEV_ELASTIC_NAME,
            'DEV_REDIS_NAME': settings.DEFAULT_DEV_REDIS_NAME,
            'DEV_CASSANDRA_NAME': settings.DEFAULT_DEV_CASSANDRA_NAME,
        })

    @cached_property
    def user_context(self):
        if self.user_context_path.exists():
            return load_context(self.user_context_path)
        else:
            return Context()


class BaseRepoContextFactory:
    def __init__(self, project_dir):
        self.project_dir = project_dir
        self.user_context_path = get_user_context_path()

    def get(self):
        context = Context()
        context.update(self.git_info)
        context.update(self.project_context)
        context.update(GlobalContextFactory().get())
        return upper_keys(context)

    @property
    def project_context(self):
        raise NotImplementedError

    @cached_property
    def git_info(self):
        repo = git.Repo(str(self.project_dir))
        origin_url = repo.remotes.origin.url
        return Context({
            'GIT_REMOTE_URL': origin_url,
            'GIT_REPO_NAME': origin_url.split('/')[-1]
        })


def get_user_context_path():
    """
    Helper for legacy sw-cli support.
    TODO: remove legacy
    """
    user_context_path = pathlib.Path.home() / settings.DEFAULT_KUBEYARD_USER_CONTEXT_FILEPATH
    if not user_context_path.exists():
        legacy_context_path = pathlib.Path.home() / settings.DEFAULT_SWCLI_USER_CONTEXT_FILEPATH
        if legacy_context_path.exists():
            logger.warning("Using legacy file: {}. Please rename it to: {}!".format(
                settings.DEFAULT_SWCLI_USER_CONTEXT_FILEPATH,
                settings.DEFAULT_KUBEYARD_USER_CONTEXT_FILEPATH,
            ))
            user_context_path = legacy_context_path
    return user_context_path


PromptedContext = collections.namedtuple('PromptedContext', ['variable', 'prompt', 'default'])


class EmptyRepoContextFactory(BaseRepoContextFactory):
    def __init__(self, project_dir, prompted_context):
        super().__init__(project_dir)
        self.prompted_context = prompted_context

    @cached_property
    def project_context(self):
        docker_image = self.git_info['GIT_REPO_NAME']
        context = {'DOCKER_IMAGE_NAME': docker_image}
        for prompt_config in self.prompted_context:
            context[prompt_config.variable] = io_utils.default_input(
                prompt_config.prompt,
                prompt_config.default.format(docker_image)
            )
        context['DOCKER_REGISTRY_DOMAIN'] = context['DOCKER_REGISTRY_NAME'].split('/', 1)[0]
        return context


class InitialisedRepoContextFactory(BaseRepoContextFactory):
    def __init__(self, project_dir, context_filepath=settings.DEFAULT_KUBEYARD_CONTEXT_FILEPATH):
        super().__init__(project_dir)
        self.context_filepath = context_filepath
        self.filename = project_dir / context_filepath
        if not self.filename.exists() and context_filepath == settings.DEFAULT_KUBEYARD_CONTEXT_FILEPATH:
            # TODO: remove legacy
            logger.warning("Using legacy file: {} file. Please rename it to: {}!".format(
                settings.DEFAULT_SWCLI_CONTEXT_FILEPATH,
                settings.DEFAULT_KUBEYARD_CONTEXT_FILEPATH,
            ))
            self.filename = project_dir / settings.DEFAULT_SWCLI_CONTEXT_FILEPATH
        if not self.filename.exists():
            raise FileNotFoundError("File does not exist: %s" % self.filename)

    @cached_property
    def project_context(self):
        context = Context({
            'PROJECT_DIR': str(self.project_dir),
            'KUBEYARD_CONTEXT_FILEPATH': self.context_filepath,
            'KUBEYARD_SCRIPTS_DIR': settings.DEFAULT_KUBEYARD_SCRIPTS_DIR,
            'KUBERNETES_DEV_SECRETS_DIR': settings.DEFAULT_KUBERNETES_DEV_SECRETS_DIR,
            'DEV_TLD': settings.DEFAULT_DEV_TLD,
            'DEV_DOMAINS': settings.DEFAULT_DEV_DOMAINS,
            'TEST_DATABASE_IMAGE': settings.DEFAULT_TEST_DATABASE_IMAGE,
            'TEST_DATABASE_NAME': settings.DEFAULT_TEST_DATABASE_NAME,
            'TEST_MIGRATION_COMMAND': settings.DEFAULT_TEST_MIGRATION_COMMAND,
            'TEST_COMMAND': settings.DEFAULT_TEST_COMMAND,
        })
        context.update(self.saved_context)
        return context

    @cached_property
    def saved_context(self):
        return load_context(self.filename)


def load_context(path):
    with path.open() as fp:
        return de_legacy(upper_keys(yaml.load(fp)))


def upper_keys(d):
    ret = Context()
    for k, v in d.items():
        ret.update({k.upper(): v})
    return ret


def de_legacy(context: Context) -> Context:
    """
    :param context: ready context with capital letters keys.
    :return: context with keys renamed from ..._SWCLI_.. to ..._KUBEYARD_...
    TODO: remove legacy
    """
    new_context = Context()
    for key, value in context.items():
        if 'SWCLI' in key:
            legacy_key = key
            key = key.replace('SWCLI', 'KUBEYARD')
            logger.warning("You have legacy entry: {} in context. Please rename it to: {}!".format(legacy_key, key))
        new_context.update({key: value})
    return new_context
