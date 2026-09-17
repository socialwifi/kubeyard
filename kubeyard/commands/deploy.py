import logging
import os
import sys
import tempfile

import kubepy.appliers
import sh

from cached_property import cached_property
from kubepy import appliers_options
from kubepy import definition_manager

from kubeyard import aliases
from kubeyard import base_command
from kubeyard import kubernetes
from kubeyard import node_ports
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
    context_vars = ["build_url", "aws_credentials", "gcs_service_key_file", "azure_connection_string", "bucket_name",
                    "upload_local_binary_path"]

    def __init__(self, *, build_url, gcs_service_key_file, aws_credentials, azure_connection_string, bucket_name,
                 upload_local_binary_path, **kwargs):
        super().__init__(**kwargs)
        self.build_url = build_url
        self.gcs_service_key_file = gcs_service_key_file
        self.aws_credentials = aws_credentials
        self.azure_connection_string = azure_connection_string
        self.bucket_name = bucket_name
        self.upload_local_binary_path = upload_local_binary_path

    def run_default(self):
        if self.should_deploy_statics:
            self.run_statics_deploy()
        database_created = False
        if self.definition_directories:
            if self.dev_requirements and self.is_development:
                database_created = self.run_dev_requirements_deploy()
            self.run_kubernetes_deploy()
        if self.is_development:
            DomainConfigurator(self.context).configure()
        if self.should_seed(database_created):
            from kubeyard.commands.seed import SeedRunner
            SeedRunner(self.context).wait_and_seed(self.deployment_names)

    def should_seed(self, database_created) -> bool:
        """
        database_created comes from createdb succeeding, so it is never true for a
        database that already holds data.
        """
        return bool(database_created and self.context.get('DEV_SEED_COMMAND'))

    @property
    def namespace(self):
        return self.context.get('KUBEYARD_NAMESPACE', '')

    @property
    def deployment_names(self):
        return [name for kind, name in owned_objects(self.definition_directories) if kind == 'Deployment']

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
            self.azure_connection_string,
            self.bucket_name,
            self.upload_local_binary_path,
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
            namespace=self.namespace,
        )
        kubernetes.install_secrets(self.context)
        if self.namespace:
            self.remove_shadowed_aliases()
        logger.info('Applying Kubernetes definitions from YAML files...')
        applier = kubepy.appliers.DirectoriesApplier(self.definition_directories, options)
        self.report_skipped(applier)
        applier.apply_all(skip=self.skip_predicate)
        logger.info('Kubernetes definitions applied')

    def report_skipped(self, applier):
        """Warn, with the reason, about each definition that will be skipped."""
        if not self.skip_predicate:
            return
        allocated = self._allocated_node_ports
        for definition in applier.definitions_to_skip(self.skip_predicate):
            logger.warning(node_ports.skip_reason(definition, allocated, self.namespace))

    def remove_shadowed_aliases(self):
        """Remove only the aliases this deploy replaces: a Service it skips shadows nothing."""
        names = owned_service_names(self.definition_directories, skip=self.skip_predicate)
        if names:
            aliases.delete(self.namespace, names)

    @cached_property
    def _allocated_node_ports(self):
        return node_ports.allocated_node_ports()

    @cached_property
    def skip_predicate(self):
        if not self.namespace:
            return None
        return node_ports.skip_predicate(self._allocated_node_ports, self.namespace)

    @property
    def definition_directories(self):
        return definition_directories(self.project_dir, include_dev_overrides=self.is_development)

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
        database_created = dispatcher.dispatch_all(self.dev_requirements)
        logger.info('Development requirements are satisfied')
        return database_created

    @property
    def dev_requirements(self):
        return self.context.get('DEV_REQUIREMENTS')


def definition_directories(project_dir, *, include_dev_overrides):
    """Shared by deploy and undeploy, so the two cannot drift on which directories are in scope."""
    kubernetes_dir = project_dir / settings.DEFAULT_KUBERNETES_DEPLOY_DIR
    overrides_dir = project_dir / settings.DEFAULT_KUBERNETES_DEV_DEPLOY_OVERRIDES_DIR
    directories = []
    if kubernetes_dir.exists():
        directories.append(kubernetes_dir)
    if include_dev_overrides and overrides_dir.exists():
        directories.append(overrides_dir)
    return directories


def _merged_definitions(directories):
    """
    kubepy's own manager does the merging, because undeploy must remove exactly what
    deploy created and an override is usually a fragment with no kind or name of its own.
    """
    manager = definition_manager.OverridenDefinitionManager(
        *(definition_manager.DefinitionManager(directory) for directory in directories),
    )
    return dict(manager)


def owned_objects(directories, skip=None):
    """List (kind, name) pairs this project owns, in definition-name order, minus any the predicate skips."""
    definitions = _merged_definitions(directories)
    owned = []
    for name in sorted(definitions):
        definition = definitions[name] or {}
        if skip is not None and skip(definition):
            continue
        kind = definition.get('kind')
        object_name = definition.get('metadata', {}).get('name')
        if kind and object_name:
            owned.append((kind, object_name))
    return owned


def owned_service_names(directories, skip=None):
    return [name for kind, name in owned_objects(directories, skip) if kind == 'Service']


class DomainConfigurator:
    hosts_watermark = '# The following line is added by kubeyard\n'
    host_format = '{minikube_ip}\t{domain}\n'
    hosts_filename = '/etc/hosts'
    WORKSPACE_DOMAIN_SEGMENT = 'ws'

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
        with open(self.hosts_filename) as hosts_file:
            content = hosts_file.read()
        for domain in self.custom_domains_to_be_configured:
            hosts_entry = self.host_format.format(minikube_ip=self.minikube_ip, domain=domain)
            content += self.hosts_watermark + hosts_entry
        self.replace_hosts_file(content)

    @cached_property
    def minikube_ip(self) -> str:
        return sh.kubectl.get.nodes(
            '-l', 'minikube.k8s.io/name=minikube',
            '-o', 'jsonpath={.items[*].status.addresses[?(@.type=="InternalIP")].address}').strip()

    def domains_for(self, workspace_name) -> list:
        top_level_domain = self.context['DEV_TLD']
        if workspace_name:
            suffix = '{}.{}.{}'.format(workspace_name, self.WORKSPACE_DOMAIN_SEGMENT, top_level_domain)
        else:
            suffix = top_level_domain
        return ['{}.{}'.format(domain, suffix) for domain in self.context['DEV_DOMAINS']]

    @property
    def all_domains(self) -> list:
        return self.domains_for(self.context.get('KUBEYARD_WORKSPACE', ''))

    @cached_property
    def custom_domains_to_be_configured(self) -> [str]:
        return [domain for domain in self.all_domains if not self.domain_exists_in_hosts(domain)]

    def remove(self, workspace_name):
        if not workspace_name:
            raise ValueError(
                'workspace_name must not be empty: an empty name would resolve to the plain, '
                'non-workspace domains and strip the shared /etc/hosts entries.')
        domains = set(self.domains_for(workspace_name))
        if not domains:
            return
        with open(self.hosts_filename) as hosts_file:
            lines = hosts_file.readlines()
        kept = []
        removed_entries = 0
        index = 0
        while index < len(lines):
            line = lines[index]
            is_watermark = line == self.hosts_watermark
            next_line = lines[index + 1] if index + 1 < len(lines) else ''
            if is_watermark and any(domain in next_line.split() for domain in domains):
                index += 2
                removed_entries += 1
                continue
            if any(domain in line.split() for domain in domains):
                index += 1
                removed_entries += 1
                continue
            kept.append(line)
            index += 1
        if removed_entries:
            logger.info('Removing {} host entries for workspace "{}"...'.format(
                removed_entries, workspace_name))
            self.replace_hosts_file(''.join(kept))

    def replace_hosts_file(self, content):
        with tempfile.NamedTemporaryFile('w', prefix='kubeyard-hosts-', delete=False) as new_hosts:
            new_hosts.write(content)
        try:
            sh.sudo('cp', new_hosts.name, self.hosts_filename, _fg=True)
        finally:
            os.unlink(new_hosts.name)

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


def static_files_storage_factory(context, image, gcs_service_key_file, aws_credentials, azure_connection_string,
                                 bucket_name, local_binary_path):
    statics_directory = context.get('STATICS_DIRECTORY', '')
    collect_statics_command = context.get('COLLECT_STATICS_COMMAND', 'collect_statics_tar')
    docker_runner = DockerRunner(context)
    bucket_name = bucket_name or context.get('BUCKET_NAME')
    arguments = {
        'statics_directory': statics_directory,
        'collect_statics_command': collect_statics_command,
        'image': image,
        'docker_runner': docker_runner,
        'bucket_name': bucket_name,
        'local_binary_path': local_binary_path,
    }
    if bucket_name:
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
        elif azure_connection_string:
            return AzureFilesStorage(
                **arguments,
                connection_string=azure_connection_string,
            )
        else:
            raise base_command.CommandException(
                'Static file storage credential/secrets required when using bucket name!',
            )
    else:
        return None


class FilesStorage:
    def __init__(self, statics_directory, collect_statics_command, image, docker_runner, local_binary_path):
        self.statics_directory = statics_directory
        self.collect_statics_command = collect_statics_command
        self.image = image
        self.docker_runner = docker_runner
        self.local_binary_path = local_binary_path

    def collect_and_upload(self):
        statics_tar_process = self.get_statics_tar_process()
        logger.info(f'Uploading to {self.__class__.__name__}...')
        if self.local_binary_path:
            self.upload_tarred_files_with_local(statics_tar_process)
        else:
            self.upload_tarred_files(statics_tar_process)

    def get_statics_tar_process(self):
        return self.docker_runner.run(
            'run', '-i', '--rm', self.image, self.collect_statics_command, _err=sys.stdout.buffer, _piped=True)

    def upload_tarred_files(self, statics_tar_process):
        raise NotImplementedError

    def upload_tarred_files_with_local(self, statics_tar_process):
        raise NotImplementedError(
            'This storage currently does not support uploading tarred files with local binary.',
        )

    def _save_tar_to_volume(self, tar_process, volume_name):
        self.docker_runner.run_with_output(
            tar_process,
            'run', '-i', '--rm',
            '-v', '{}:/extracted/'.format(volume_name),
            'busybox:1.28.0',
            'tar', 'xf', '-', '-C', '/extracted/',
        )


class GCSFilesStorage(FilesStorage):
    cloud_sdk_image = 'google/cloud-sdk:183.0.0'

    def __init__(self, statics_directory, collect_statics_command, image, docker_runner, local_binary_path,
                 service_key_file, bucket_name):
        super().__init__(statics_directory, collect_statics_command, image, docker_runner, local_binary_path)
        self.service_key_file = service_key_file
        self.bucket_name = bucket_name

    def upload_tarred_files(self, statics_tar_process):

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
                'rsync', '-c', '-r',
                '/upload/', 'gs://{}/{}'.format(self.bucket_name, self.statics_directory),
            )


class S3FilesStorage(FilesStorage):
    def __init__(self, statics_directory, collect_statics_command, image, docker_runner, local_binary_path,
                 credentials, bucket_name):
        super().__init__(statics_directory, collect_statics_command, image, docker_runner, local_binary_path)
        self.bucket_name = bucket_name
        if ':' in credentials:
            self.access_key, self.secret_key = credentials.split(':', 2)
        else:
            raise base_command.CommandException('AWS credentials should be in form access_key:secret_key.')

    def upload_tarred_files(self, statics_tar_process):
        upload_statics_run_command = [
            'run', '-i', '--rm',
            '-e', 'AWS_ACCESS_KEY={}'.format(self.access_key),
            '-e', 'AWS_SECRET_KEY={}'.format(self.secret_key),
            '-e', 'UPLOAD_BUCKET={}'.format(self.bucket_name),
            '-e', 'UPLOAD_PATH={}/'.format(self.statics_directory),
            'socialwifi/aws-utils:1.0.0', 'upload_tar',
        ]
        self.docker_runner.run_with_output(statics_tar_process, *upload_statics_run_command)


class AzureFilesStorage(FilesStorage):
    azure_cli_image = 'microsoft/azure-cli:2.0.61'

    def __init__(self, statics_directory, collect_statics_command, image, docker_runner, local_binary_path,
                 connection_string, bucket_name):
        super().__init__(statics_directory, collect_statics_command, image, docker_runner, local_binary_path)
        self.connection_string = connection_string
        self.bucket_name = bucket_name

    def upload_tarred_files(self, statics_tar_process):
        with self.docker_runner.temporary_volume() as volume_name:
            self._save_tar_to_volume(statics_tar_process, volume_name)
            self.docker_runner.run_with_output(
                'run', '-i', '--rm',
                '-v', '{}:/upload/:ro'.format(volume_name),
                self.azure_cli_image,
                'az',
                'storage',
                'blob',
                'upload-batch',
                '--connection-string', self.connection_string,
                '--destination', self.bucket_name,
                '--source', '/upload',
                '--destination-path', self.statics_directory,
            )

    def upload_tarred_files_with_local(self, statics_tar_process):
        statics_absolute_path = '{}/upload'.format(sh.pwd().strip())
        self._save_tar_to_volume(statics_tar_process, statics_absolute_path)
        sh.bash(
            '-c',
            " ".join([
                self.local_binary_path,
                'storage',
                'blob',
                'upload-batch',
                '--connection-string', '"{}"'.format(self.connection_string),
                '--destination', self.bucket_name,
                '--source', statics_absolute_path,
                '--destination-path', self.statics_directory,
            ]),
            _out=sys.stdout.buffer, _err=sys.stdout.buffer,
        )
