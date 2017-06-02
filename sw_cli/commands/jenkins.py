import getpass
import jenkins
from cached_property import cached_property
from sw_cli import settings
from sw_cli import base_command
from sw_cli import files_generator


class JenkinsCommand(base_command.BaseCommand):
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

    def print_info(self):
        print(self.server.get_whoami())

    def init_job(self):
        job_name = self.context['DOCKER_IMAGE_NAME']
        print("Initialising jenkins job: %s" % job_name)
        config_filepath = self.context.get('JENKINS_JOB_CONFIG_FILEPATH', settings.DEFAULT_JENKINS_JOB_CONFIG_FILEPATH)
        self.server.create_job(job_name, self.get_config_xml(config_filepath))
        config_filepath = self.context.get('JENKINS_JOB_TEST_PATCHSET_FILEPATH',
                                           settings.DEFAULT_JENKINS_JOB_TEST_PATCHSET_FILEPATH)
        self.server.create_job('{} test patchset'.format(job_name), self.get_config_xml(config_filepath))

    def reconfig_job(self):
        job_name = self.context['DOCKER_IMAGE_NAME']
        print("Reconfiguring jenkins job: %s" % job_name)
        config_filepath = self.context.get('JENKINS_JOB_CONFIG_FILEPATH', settings.DEFAULT_JENKINS_JOB_CONFIG_FILEPATH)
        self.server.reconfig_job(job_name, self.get_config_xml(config_filepath))
        config_filepath = self.context.get('JENKINS_JOB_TEST_PATCHSET_FILEPATH',
                                           settings.DEFAULT_JENKINS_JOB_TEST_PATCHSET_FILEPATH)
        self.server.reconfig_job('{} test patchset'.format(job_name), self.get_config_xml(config_filepath))

    def build_job(self):
        job_name = self.context['DOCKER_IMAGE_NAME']
        print("building jenkins job: %s" % job_name)
        self.server.build_job(job_name)


def init(args):
    print("Starting command jenkins_init")
    cmd = JenkinsCommand(args)
    cmd.init_job()
    print("Done.")


def reconfig(args):
    print("Starting command jenkins_reconfig")
    cmd = JenkinsCommand(args)
    cmd.reconfig_job()
    print("Done.")


def build(args):
    print("Starting command jenkins_build")
    cmd = JenkinsCommand(args)
    cmd.build_job()
    print("Done.")


def info(args):
    print("Starting command jenkins_info")
    cmd = JenkinsCommand(args)
    cmd.print_info()
    print("Done.")
