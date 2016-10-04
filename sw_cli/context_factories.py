import os

from cached_property import cached_property
import yaml
import git

from sw_cli import settings


class BaseContextFactory:
    def __init__(self, project_dir):
        self.project_dir = project_dir

    def get(self):
        context = {}
        context.update(self.git_info)
        context.update(self.jenkins_info)
        context.update(self.project_context)
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

    @cached_property
    def jenkins_info(self):
        return {
            'JENKINS_URL': settings.DEFAULT_JENKINS_URL,
            'JENKINS_EMAIL_RECIPIENTS': settings.DEFAULT_JENKINS_EMAIL_RECIPIENTS,
        }


class EmptyRepoContextFactory(BaseContextFactory):
    @cached_property
    def project_context(self):
        docker_image = self.git_info['GIT_REPO_NAME']

        service_name = input('service name [%s]: ' % settings.DEFAULT_KUBE_SERVICE_NAME_PATTERN.format(docker_image))
        service_name = service_name or settings.DEFAULT_KUBE_SERVICE_NAME_PATTERN.format(docker_image)

        service_port = input('service port [%s]: ' % settings.DEFAULT_KUBE_SERVICE_PORT)
        service_port = service_port or settings.DEFAULT_KUBE_SERVICE_PORT

        return dict(
            DOCKER_IMAGE_NAME=docker_image,
            KUBE_SERVICE_NAME=service_name,
            KUBE_SERVICE_PORT=service_port
        )


class InitialisedRepoContextFactory(BaseContextFactory):
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
            'SWCLI_DEVEL_BUILD_SCRIPT_PATH': settings.DEFAULT_SWCLI_DEVEL_BUILD_SCRIPT_PATH,
            'SWCLI_DEVEL_TEST_SCRIPT_PATH': settings.DEFAULT_SWCLI_DEVEL_TEST_SCRIPT_PATH,
            'SWCLI_DEVEL_DEPLOY_SCRIPT_PATH': settings.DEFAULT_SWCLI_DEVEL_DEPLOY_SCRIPT_PATH
        }
        context.update(self.saved_context)
        return context

    @cached_property
    def saved_context(self):
        with self.filename.open() as fp:
            return upper_keys(yaml.load(fp))


def upper_keys(d):
    ret = dict()
    for k, v in d.items():
        ret.update({k.upper(): v})
    return ret
