import getpass
import logging
import sys

import kubepy.appliers
import sh

from cached_property import cached_property
from kubepy import appliers_options

from kubeyard import base_command
from kubeyard import kubernetes
from kubeyard import settings
from kubeyard.commands.devel import MAX_JOB_RETRIES
from kubeyard.commands.devel import BaseDevelCommand
from kubeyard.commands.devel import DockerRunner

logger = logging.getLogger(__name__)


class DeployCommand(BaseDevelCommand):
    """
    Deploys application to kubernetes.

    Next step is creating secret. Secret is named KUBE_SERVICE_NAME configured through context. its content is gathered
    either form repository in development mode or from global directory in production mode (see kubeyard help setup).
    key value pairs of this secrets are collected from files in this directory: keys are filenames and values are
    contents of these files. File secrets.yml is exception: it contains yaml encoded dictionary of additional key,
    value pairs. In genereal you should use secrets.yml for your short text secrets.

    Last step is deploying ./config/kubernetes/deploy/ using kubepy_deploy_all command
    (https://github.com/socialwifi/kubepy/). In development mode it also merges differences from
    config/development_overrides, and adds volumes to every pod configured in dev_mounted_paths in config/kubeyard.yml.
    These volumes should be mounted in selected pods using development_overrides.

    \b
    Example:
    dev_mounted_paths:
    - name: dev-volume
      host-path: docker/source

    Can be overridden in <project_dir>/sripts/deploy.
    """
    custom_script_name = 'deploy'
    context_vars = ["build_url", "aws_credentials", "gcs_service_key_file", "bucket_name"]

    def __init__(self, *, build_url, gcs_service_key_file, aws_credentials, bucket_name, **kwargs):
        super().__init__(**kwargs)
        self.build_url = build_url
        self.gcs_service_key_file = gcs_service_key_file
        self.aws_credentials = aws_credentials
        self.bucket_name = bucket_name

    def run_default(self):
        if self.should_deploy_statics:
            self.run_statics_deploy()
        if self.definition_directories:
            if self.dev_requirements and self.is_development:
                self.run_dev_requirements_deploy()
            self.run_kubernetes_deploy()
        if self.is_development:
            DomainConfigurator(self.context).configure()

    @property
    def should_deploy_statics(self):
        return not self.is_development and self.static_files_storage

    @cached_property
    def static_files_storage(self):
        return static_files_storage_factory(
            self.context,
            self.image,
            self.gcs_service_key_file,
            self.aws_credentials,
            self.bucket_name,
        )

    def run_statics_deploy(self):
        logger.info('Uploading static files...')
        self.static_files_storage.collect_and_upload()
        logger.info('Static files uploaded')

    def run_kubernetes_deploy(self):
        pod_annotations = {}
        if self.build_url is not None:
            pod_annotations['kubeyard/build-url'] = self.build_url
        options = appliers_options.Options(
            build_tag=self.tag, replace=self.is_development, host_volumes=self.host_volumes,
            max_job_retries=MAX_JOB_RETRIES, pod_annotations=pod_annotations,
        )
        kubernetes.install_secrets(self.context)
        logger.info('Applying Kubernetes definitions from YAML files...')
        kubepy.appliers.DirectoriesApplier(self.definition_directories, options).apply_all()
        logger.info('Kubernetes definitions applied')

    @property
    def definition_directories(self):
        kubernetes_dir = self.project_dir / settings.DEFAULT_KUBERNETES_DEPLOY_DIR
        overrides_dir = self.project_dir / settings.DEFAULT_KUBERNETES_DEV_DEPLOY_OVERRIDES_DIR
        definition_directories = []
        if kubernetes_dir.exists():
            definition_directories.append(kubernetes_dir)
        if self.is_development and overrides_dir.exists():
            definition_directories.append(overrides_dir)
        return definition_directories

    @property
    def host_volumes(self):
        if self.is_development:
            mounted_project_dir = self.cluster.get_mounted_project_dir(self.project_dir)
            return {
                volume['name']: mounted_project_dir / volume['host-path']
                for volume in self.context.get('DEV_MOUNTED_PATHS', [])
            }
        else:
            return {}

    def run_dev_requirements_deploy(self):
        logger.info('Checking development requirements...')
        from kubeyard.commands.dev_requirements import RequirementsDispatcher
        dispatcher = RequirementsDispatcher(self.context)
        dispatcher.dispatch_all(self.dev_requirements)
        logger.info('Development requirements are satisfied')

    @property
    def dev_requirements(self):
        return self.context.get('DEV_REQUIREMENTS')


class DomainConfigurator:
    hosts_watermark = '# The following line is added by kubeyard\n'
    host_format = '{minikube_ip}\t{domain}\n'
    hosts_filename = '/etc/hosts'

    def __init__(self, context: dict):
        self.context = context

    def configure(self):
        if self.custom_domains_to_be_configured:
            logger.info(
                f'{len(self.custom_domains_to_be_configured)} domains need to be configured: '
                f'{self.custom_domains_to_be_configured}. '
                f'Updating {self.hosts_filename}...',
            )
            self.run_update_hosts()
        else:
            logger.info('All domains already configured, no action required.')

    def run_update_hosts(self):
        for domain in self.custom_domains_to_be_configured:
            hosts_entry = self.host_format.format(minikube_ip=self.minikube_ip, domain=domain)
            sh.sudo(
                '-S',
                'tee', '--append', self.hosts_filename,
                _in=self._sudo_password + self.hosts_watermark + hosts_entry,
            )

    @cached_property
    def minikube_ip(self) -> str:
        return sh.minikube('ip').strip()

    @cached_property
    def _sudo_password(self):
        prompt = f"[sudo] password for {getpass.getuser()}: "
        return getpass.getpass(prompt=prompt) + "\n"

    @cached_property
    def custom_domains_to_be_configured(self) -> [str]:
        result = []
        top_level_domain = self.context['DEV_TLD']
        for domain in self.context['DEV_DOMAINS']:
            domain = f'{domain}.{top_level_domain}'
            if not self.domain_exists_in_hosts(domain):
                result.append(domain)
        return result

    def domain_exists_in_hosts(self, domain: str) -> bool:
        previous_line = ''
        with open(self.hosts_filename) as hosts_file:
            for line in hosts_file:
                if domain in line:
                    if previous_line != self.hosts_watermark:
                        logger.warning(f'Hostname: {domain} not added by kubeyard, please remove manually added entry.')
                    return True
                previous_line = line
        return False


def static_files_storage_factory(context, image, gcs_service_key_file, aws_credentials, bucket_name):
    statics_directory = context.get('STATICS_DIRECTORY')
    collect_statics_command = context.get('COLLECT_STATICS_COMMAND', 'collect_statics_tar')
    docker_runner = DockerRunner(context)
    bucket_name = bucket_name or context.get('BUCKET_NAME')
    arguments = {
        'statics_directory': statics_directory,
        'collect_statics_command': collect_statics_command,
        'image': image,
        'docker_runner': docker_runner,
        'bucket_name': bucket_name,
    }
    if statics_directory and bucket_name:
        if gcs_service_key_file:
            return GCSFilesStorage(
                **arguments,
                service_key_file=gcs_service_key_file,
            )
        elif aws_credentials:
            return S3FilesStorage(
                **arguments,
                credentials=aws_credentials,
            )
        else:
            raise base_command.CommandException(
                'Static file storage credential/secrets required when using bucket name!',
            )
    else:
        return None


class FilesStorage:
    def __init__(self, statics_directory, collect_statics_command, image, docker_runner):
        self.statics_directory = statics_directory
        self.collect_statics_command = collect_statics_command
        self.image = image
        self.docker_runner = docker_runner

    def collect_and_upload(self):
        statics_tar_process = self.get_statics_tar_process()
        self.upload_tarred_files(statics_tar_process)

    def get_statics_tar_process(self):
        return self.docker_runner.run(
            'run', '-i', '--rm', self.image, self.collect_statics_command, _err=sys.stdout.buffer, _piped=True)

    def upload_tarred_files(self, statics_tar_process):
        raise NotImplementedError


class GCSFilesStorage(FilesStorage):
    cloud_sdk_image = 'google/cloud-sdk:183.0.0'

    def __init__(self, statics_directory, collect_statics_command, image, docker_runner, service_key_file, bucket_name):
        super().__init__(statics_directory, collect_statics_command, image, docker_runner)
        self.service_key_file = service_key_file
        self.bucket_name = bucket_name

    def upload_tarred_files(self, statics_tar_process):
        logger.info('Uploading to GCS...')
        with self.docker_runner.temporary_volume() as volume_name:
            self._save_tar_to_volume(statics_tar_process, volume_name)
            self.docker_runner.run_with_output(
                'run', '-i', '--rm',
                '-v', '{}:/service-account.json:ro'.format(self.service_key_file),
                '-v', '{}:/upload/:ro'.format(volume_name),
                self.cloud_sdk_image,
                'gsutil',
                '-m',
                '-o', 'Credentials:gs_service_key_file=/service-account.json',
                'cp', '-r', '/upload/*', 'gs://{}/{}/'.format(self.bucket_name, self.statics_directory),
            )

    def _save_tar_to_volume(self, tar_process, volume_name):
        self.docker_runner.run_with_output(
            tar_process,
            'run', '-i', '--rm',
            '-v', '{}:/extracted/'.format(volume_name),
            'busybox:1.28.0',
            'tar', 'xf', '-', '-C', '/extracted/',
        )


class S3FilesStorage(FilesStorage):
    def __init__(self, statics_directory, collect_statics_command, image, docker_runner, credentials, bucket_name):
        super().__init__(statics_directory, collect_statics_command, image, docker_runner)
        self.bucket_name = bucket_name
        if ':' in credentials:
            self.access_key, self.secret_key = credentials.split(':', 2)
        else:
            raise base_command.CommandException('AWS credentials should be in form access_key:secret_key.')

    def upload_tarred_files(self, statics_tar_process):
        logger.info('Uploading to AWS S3...')
        upload_statics_run_command = [
            'run', '-i', '--rm',
            '-e', 'AWS_ACCESS_KEY={}'.format(self.access_key),
            '-e', 'AWS_SECRET_KEY={}'.format(self.secret_key),
            '-e', 'UPLOAD_BUCKET={}'.format(self.bucket_name),
            '-e', 'UPLOAD_PATH={}/'.format(self.statics_directory),
            'socialwifi/aws-utils:1.0.0', 'upload_tar',
        ]
        self.docker_runner.run_with_output(statics_tar_process, *upload_statics_run_command)
