import pathlib
from cached_property import cached_property
import yaml
import git

from sw_cli import io_utils
from sw_cli import settings


class GlobalContextFactory:
    def __init__(self):
        self.user_context_path = pathlib.Path.home() / settings.DEFAULT_SWCLI_USER_CONTEXT_FILEPATH

    def get(self):
        context = {}
        context.update(self.jenkins_info)
        context.update(self.base_user_context)
        context.update(self.user_context)
        return upper_keys(context)

    @cached_property
    def jenkins_info(self):
        return {
            'JENKINS_URL': settings.DEFAULT_JENKINS_URL,
            'JENKINS_EMAIL_RECIPIENTS': settings.DEFAULT_JENKINS_EMAIL_RECIPIENTS,
        }

    @cached_property
    def base_user_context(self):
        return {
            'SWCLI_USER_CONTEXT_FILEPATH': str(self.user_context_path),
            'SWCLI_MODE': 'production',
            'DEV_POSTGRES_NAME': settings.DEFAULT_DEV_POSTGRES_NAME,
            'DEV_PUBSUB_NAME': settings.DEFAULT_DEV_PUBSUB_NAME,
            'DEV_REDIS_NAME': settings.DEFAULT_DEV_REDIS_NAME,
        }

    @cached_property
    def user_context(self):
        if self.user_context_path.exists():
            return load_context(self.user_context_path)
        else:
            return {}


class BaseRepoContextFactory:
    def __init__(self, project_dir):
        self.project_dir = project_dir
        self.user_context_path = pathlib.Path.home() / settings.DEFAULT_SWCLI_USER_CONTEXT_FILEPATH

    def get(self):
        context = {}
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
        return {
            'GIT_REMOTE_URL': origin_url,
            'GIT_REPO_NAME': origin_url.split('/')[-1]
        }


class EmptyRepoContextFactory(BaseRepoContextFactory):
    @cached_property
    def project_context(self):
        docker_image = self.git_info['GIT_REPO_NAME']

        service_name = io_utils.default_input('service name', settings.DEFAULT_KUBE_SERVICE_NAME_PATTERN.format(docker_image))
        service_port = io_utils.default_input('service port', settings.DEFAULT_KUBE_SERVICE_PORT)

        return dict(
            DOCKER_IMAGE_NAME=docker_image,
            KUBE_SERVICE_NAME=service_name,
            KUBE_SERVICE_PORT=service_port
        )


class InitialisedRepoContextFactory(BaseRepoContextFactory):
    def __init__(self, project_dir, context_filepath=settings.DEFAULT_SWCLI_CONTEXT_FILEPATH):
        super().__init__(project_dir)
        self.context_filepath = context_filepath
        self.filename = project_dir / context_filepath
        if not self.filename.exists():
            raise FileNotFoundError("file does not exist: %s" % self.filename)

    @cached_property
    def project_context(self):
        context = {
            'PROJECT_DIR': str(self.project_dir),
            'SWCLI_CONTEXT_FILEPATH': self.context_filepath,
            'SWCLI_SCRIPTS_DIR': settings.DEFAULT_SWCLI_SCRIPTS_DIR,
            'KUBERNETES_DEV_SECRETS_DIR': settings.DEFAULT_KUBERNETES_DEV_SECRETS_DIR,
        }
        context.update(self.saved_context)
        return context

    @cached_property
    def saved_context(self):
        return load_context(self.filename)


def load_context(path):
    with path.open() as fp:
        return upper_keys(yaml.load(fp))


def upper_keys(d):
    ret = dict()
    for k, v in d.items():
        ret.update({k.upper(): v})
    return ret
