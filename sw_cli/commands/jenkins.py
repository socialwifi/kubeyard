import getpass
import logging

import jenkins
from cached_property import cached_property
from sw_cli import settings
from sw_cli import base_command
from sw_cli import files_generator


logger = logging.getLogger(__name__)


class JenkinsCommand(base_command.InitialisedRepositoryCommand):
    def run(self):
        super().run()

    @cached_property
    def server(self):
        username, password = self.get_credentials()
        return jenkins.Jenkins(self.context.get('JENKINS_URL', settings.DEFAULT_JENKINS_URL),
                               username=username, password=password)

    def get_credentials(self):
        username = input('Username: ')
        password = getpass.getpass(prompt='Password: ', stream=None)
        return username, password

    def get_config_xml(self, config_filepath):
        filename = self.project_dir / config_filepath
        if not filename.exists():
            raise base_command.CommandException("Could not find jenkins job configuration: %s. Exiting." % filename)
        template = files_generator.jinja_environment.get_template(str(filename))
        return template.render(self.context)


class JenkinsInfoCommand(JenkinsCommand):
    """
    Displays info about jenkins user.
    """
    def run(self):
        super().run()
        print(self.server.get_whoami())


class JenkinsInitCommand(JenkinsCommand):
    """
    Creates jenkins jobs (deploy and test patchset) defined in repository. Requires administrative privileges on
    jenkins.
    """
    def run(self):
        super().run()
        job_name = self.context['DOCKER_IMAGE_NAME']
        logger.info('Creating Jenkins job: "{}"...'.format(job_name))
        config_filepath = self.context.get('JENKINS_JOB_CONFIG_FILEPATH', settings.DEFAULT_JENKINS_JOB_CONFIG_FILEPATH)
        self.server.create_job(job_name, self.get_config_xml(config_filepath))
        config_filepath = self.context.get('JENKINS_JOB_TEST_PATCHSET_FILEPATH',
                                           settings.DEFAULT_JENKINS_JOB_TEST_PATCHSET_FILEPATH)
        job_name = '{} test patchset'.format(job_name)
        logger.info('Creating Jenkins job: "{}"...'.format(job_name))
        self.server.create_job(job_name, self.get_config_xml(config_filepath))
        logger.info('Done')


class JenkinsReconfigCommand(JenkinsCommand):
    """
    Updates jenkins jobs (deploy and test patchset) defined in repository. Requires administrative privileges on
    jenkins.
    """
    def run(self):
        super().run()
        job_name = self.context['DOCKER_IMAGE_NAME']
        logger.info('Reconfiguring Jenkins job: "{}"...'.format(job_name))
        config_filepath = self.context.get('JENKINS_JOB_CONFIG_FILEPATH', settings.DEFAULT_JENKINS_JOB_CONFIG_FILEPATH)
        self.server.reconfig_job(job_name, self.get_config_xml(config_filepath))
        config_filepath = self.context.get('JENKINS_JOB_TEST_PATCHSET_FILEPATH',
                                           settings.DEFAULT_JENKINS_JOB_TEST_PATCHSET_FILEPATH)
        job_name = '{} test patchset'.format(job_name)
        logger.info('Reconfiguring Jenkins job: "{}"...'.format(job_name))
        self.server.reconfig_job(job_name, self.get_config_xml(config_filepath))
        logger.info('Done')


class JenkinsBuildCommand(JenkinsCommand):
    """
    Runs jenkins deploy job defined in repository. Requires run privileges on jenkins.
    """
    def run(self):
        super().run()
        job_name = self.context['DOCKER_IMAGE_NAME']
        logger.info('Starting jenkins job: "{}"...'.format(job_name))
        self.server.build_job(job_name)
        logger.info('Done')
