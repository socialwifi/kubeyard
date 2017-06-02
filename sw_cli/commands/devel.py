import io
import os
import sys

import kubepy.appliers
from kubepy import appliers_options
import kubepy.base_commands
import pathlib
import sh
from cached_property import cached_property

from sw_cli import base_command
from sw_cli import dependencies
from sw_cli import kubernetes
from sw_cli import minikube
from sw_cli import settings
from sw_cli.commands import custom_script

MAX_JOB_RETRIES = 10

class SilencedException(Exception):
    def __init__(self, code):
        self.code = code

class BaseDevelCommand(base_command.BaseCommand):
    docker_repository = 'docker.socialwifi.com'

    def __init__(self, args):
        super().__init__(args)
        if self.is_development:
            self._prepare_minikube()

    def run(self):
        if self.options.default:
            self.run_default()
        else:
            try:
                custom_script.CustomScriptRunner(self.project_dir, self.context).run(self.custom_script_name, self.args)
            except custom_script.CustomScriptException:
                self.run_default()

    @cached_property
    def options(self):
        parser = self.get_parser()
        return parser.parse_known_args()[0]

    def _prepare_minikube(self):
        minikube.ensure_minikube_set_up()
        self.context.update(minikube.docker_env())

    def get_parser(self):
        parser = super().get_parser()
        parser.add_argument(
            '--tag', dest='tag', action='store', default=None, help='Used image tag.')
        parser.add_argument(
            '--default', dest='default', action='store_true', default=False,
            help='Don\'t try to execute custom script. Useful when you need original behaviour in overridden method.')
        parser.add_argument(
            '--image-name', dest='image_name', action='store', default=None,
            help='Image name (without repository). Default is set in sw-cli.yml.')
        return parser

    def docker(self, *args, **kwargs):
        return sh.docker(*args, _env=self.sh_env, **kwargs)

    def docker_with_output(self, *args, **kwargs):
        try:
            return self.docker(*args, _out=sys.stdout.buffer, _err=sys.stdout.buffer, **kwargs)
        except sh.ErrorReturnCode as e:
            raise SilencedException(e.exit_code)

    @property
    def image(self):
        return '{}/{}:{}'.format(self.docker_repository, self.image_name, self.tag)

    @property
    def latest_image(self):
        return '{}/{}:latest'.format(self.docker_repository, self.image_name)

    @property
    def image_name(self):
        return self.options.image_name or self.context["DOCKER_IMAGE_NAME"]

    @property
    def tag(self):
        return self.options.tag or self.default_tag

    @property
    def default_tag(self):
        if self.is_development:
            return 'dev'
        else:
            return 'latest'

    @property
    def is_development(self):
        return self.context['SWCLI_MODE'] == 'development'

    def run_default(self):
        raise NotImplementedError

    @property
    def custom_script_name(self):
        raise NotImplementedError

    @cached_property
    def sh_env(self):
        env = os.environ.copy()
        env.update(self.context.as_environment())
        return env


class BuildCommand(BaseDevelCommand):
    custom_script_name = 'build'

    def run_default(self):
        image_context = self.options.image_context or "{0}/docker".format(self.project_dir)
        self.docker_with_output('build', '-t', self.image, image_context)

    def get_parser(self):
        parser = super().get_parser()
        parser.add_argument(
            '--image-context', dest='image_context', action='store', default=None,
            help='Image context containing Dockerfile. Defaults to <project_dir>/docker')
        return parser


class UpdateRequirementsCommand(BaseDevelCommand):
    custom_script_name = 'update_requirements'

    def get_parser(self):
        parser = super().get_parser()
        parser.add_argument('--before3.6.0-5', dest='before', action='store_true',
                            default=False, help='Add this flag to use update for an older python application.')
        return parser

    def run_default(self):
        if self.options.before is True:
            os.system(self.legacy_pip_freeze_command)
        else:
            with open("docker/requirements/python.txt", "w") as output_file:
                output_file.write(self.get_pip_freeze_output())

    @property
    def legacy_pip_freeze_command(self):
        return ('(cat docker/source/base_requirements.txt | docker run --rm -i python:3.6.0'
                ' bash -c "'
                'pip install --upgrade setuptools==34.3.0 > /dev/stderr ; '
                'pip install -r /dev/stdin > /dev/stderr ; '
                'pip freeze")'
                ' > docker/requirements.txt')

    def get_pip_freeze_output(self):
        output = io.StringIO()
        input = sh.cat("docker/source/base_requirements.txt")
        self.docker('run', '--rm', '-i', self.image, 'freeze_requirements', _in=input, _out=output,
                    _err=sys.stdout.buffer)
        return output.getvalue()


class TestCommand(BaseDevelCommand):
    custom_script_name = 'test'

    def __init__(self, args):
        super().__init__(args)
        self.context['HOST_VOLUMES'] = ' '.join(self.volumes)

    def run_default(self):
        self.docker_with_output('run', '--rm', '--net=none', *self.volumes, self.image, 'run_tests')

    @property
    def volumes(self):
        if self.is_development:
            mounted_project_dir = pathlib.Path('/hosthome') / self.project_dir.relative_to('/home')
            for volume in self.context.get('DEV_MOUNTED_PATHS', []):
                if 'mount-in-tests' in volume and volume['mount-in-tests']['image-name'] == self.image_name:
                    host_path = str(mounted_project_dir / volume['host-path'])
                    container_path = volume['mount-in-tests']['path']
                    yield from ['-v', '{}:{}:ro'.format(host_path, container_path)]


class PushCommand(BaseDevelCommand):
    custom_script_name = 'push'

    def run_default(self):
        self.docker_with_output('push', self.image)
        self.docker_with_output('tag', self.image, self.latest_image)
        self.docker_with_output('push', self.latest_image)


class DeployCommand(BaseDevelCommand):
    custom_script_name = 'deploy'

    def get_parser(self):
        parser = super().get_parser()
        parser.add_argument(
            '--aws-credentials', dest='aws_credentials', action='store', default=None,
            help='Needed to deploy static data. AWS_KEY:AWS_SECRET.')
        return parser

    def run_default(self):
        if self.statics_directory and self.aws_credentials and not self.is_development:
            self.run_statics_deploy()
        if self.definition_directories:
            self.run_kubernetes_deploy()

    def run_statics_deploy(self):
        access_key, secret_key = self.aws_credentials
        collect_statics_command = self.context.get('COLLECT_STATICS_COMMAND', 'collect_statics_tar')
        statics_tar_process = self.docker('run', '-i', '--rm', self.image, collect_statics_command, _piped=True)
        upload_statics_run_command = [
            'run', '-i', '--rm', '-e', 'AWS_ACCESS_KEY={}'.format(access_key),
            '-e',  'AWS_SECRET_KEY={}'.format(secret_key), '-e', 'UPLOAD_BUCKET=socialwifi-static',
            '-e', 'UPLOAD_PATH={}/'.format(self.statics_directory),
            'docker.socialwifi.com/aws-utils', 'upload_tar'
        ]
        self.docker_with_output(statics_tar_process, *upload_statics_run_command)

    @property
    def aws_credentials(self):
        if self.options.aws_credentials:
            if ':' in self.options.aws_credentials:
                return self.options.aws_credentials.split(':', 2)
            else:
                raise base_command.CommandException('Aws credentials should be in form access_key:secret_key.')
        else:
            return None

    @property
    def statics_directory(self):
        return self.context.get('STATICS_DIRECTORY')

    def run_kubernetes_deploy(self):
        options = appliers_options.Options(
            build_tag=self.tag, replace=self.is_development, host_volumes=self.host_volumes,
            max_job_retries=MAX_JOB_RETRIES,
        )
        kubernetes.install_secrets(self.context)
        kubepy.appliers.DirectoriesApplier(self.definition_directories, options).apply_all()

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
            mounted_project_dir = pathlib.Path('/hosthome') / self.project_dir.relative_to('/home')
            return {
                volume['name']: mounted_project_dir / volume['host-path']
                for volume in self.context.get('DEV_MOUNTED_PATHS', [])
            }
        else:
            return {}


class SetupDevDbCommand(BaseDevelCommand):
    custom_script_name = 'setup_dev_db'

    def run_default(self):
        postgres_name = self.context['DEV_POSTGRES_NAME']
        database_name = self.options.database or self.context['KUBE_SERVICE_NAME']
        self.ensure_postgres_running(postgres_name)
        self.ensure_database_present(postgres_name, database_name)

    def ensure_postgres_running(self, postgres_name):
        PostgresRunningEnsurer(self.docker, postgres_name).ensure()

    def ensure_database_present(self, postgres_name, database_name):
        try:
            self.docker('exec', postgres_name, 'createdb', database_name, '-U', 'postgres')
        except sh.ErrorReturnCode as e:
            if b'already exists' not in e.stderr:
                raise e

    def get_parser(self):
        parser = super().get_parser()
        parser.add_argument(
            '--database', dest='database', action='store', default=None, help='used database name')
        return parser


class PostgresRunningEnsurer(dependencies.ContainerRunningEnsurer):
    postgres_version = '9.6.1'
    started_log = 'PostgreSQL init process complete; ready for start up.'

    def docker_run(self):
        self.docker('run', '-d', '--restart=always',
                    '--name={}'.format(self.name),
                    '-p', '172.17.0.1:35432:5432',
                    'postgres:{}'.format(self.postgres_version))


class SetupDevElasticsearchCommand(BaseDevelCommand):
    custom_script_name = 'setup_dev_es'

    def run_default(self):
        elastic_name = self.context['DEFAULT_DEV_ELASTIC_NAME']
        self.ensure_elastic_running(elastic_name)

    def ensure_elastic_running(self, elastic_name):
        ElasticsearchRunningEnsurer(self.docker, elastic_name).ensure()


class ElasticsearchRunningEnsurer(dependencies.ContainerRunningEnsurer):
    elastic_version = '5.2.1'
    started_log = '] started'

    def docker_run(self):
        self.docker('run', '-d', '--restart=always',
                    '--name={}'.format(self.name),
                    '-e', 'ES_JAVA_OPTS=-Xms200m -Xmx200m',
                    '-p', '172.17.0.1:9300:9300',
                    '-p', '172.17.0.1:9200:9200',
                    'elasticsearch:{}'.format(self.elastic_version))


class SetupPubSubEmulatorCommand(BaseDevelCommand):
    custom_script_name = 'setup_dev_pubsub'

    def run_default(self):
        pubsub_name = self.context['DEV_PUBSUB_NAME']
        topic_name = self.options.topic or self.context['KUBE_SERVICE_NAME']
        subscription_name = self.options.subscription
        self.ensure_pubsub_running(pubsub_name)
        self.ensure_topic_present(pubsub_name, topic_name)
        if subscription_name:
            self.ensure_subscription_present(pubsub_name, topic_name, subscription_name)

    def ensure_pubsub_running(self, pubsub_name):
        PubSubRunningEnsurer(self.docker, pubsub_name).ensure()

    def ensure_topic_present(self, pubsub_name, topic_name):
        try:
            self.docker('exec', pubsub_name, 'pubsub_add_topic', topic_name)
        except sh.ErrorReturnCode as e:
            if b'Topic already exists' not in e.stderr:
                raise

    def ensure_subscription_present(self, pubsub_name, topic_name, subscription_name):
        try:
            self.docker('exec', pubsub_name, 'pubsub_add_subscription', topic_name, subscription_name)
        except sh.ErrorReturnCode as e:
            if b'Subscription already exists' not in e.stderr:
                raise

    def get_parser(self):
        parser = super().get_parser()
        parser.add_argument(
            '--topic', dest='topic', action='store', default=None)
        parser.add_argument(
            '--subscription', dest='subscription', action='store', default=None, help='if not set it wont be created')
        return parser


class PubSubRunningEnsurer(dependencies.ContainerRunningEnsurer):
    started_log = '[pubsub] INFO: Server started, listening on'
    look_in_stream = 'err'

    def docker_run(self):
        self.docker('run', '-d', '--restart=always',
                    '--name={}'.format(self.name),
                    '-p', '172.17.0.1:8042:8042',
                    'docker.socialwifi.com/sw-pubsub-emulator-helper')


class SetupDevRedisCommand(BaseDevelCommand):
    custom_script_name = 'setup_dev_redis'

    def run_default(self):
        redis_name = self.context['DEV_REDIS_NAME']
        self.ensure_redis_running(redis_name)
        self.reset_global_secrets()

    def reset_global_secrets(self):
        manipulator = kubernetes.get_global_secrets_manipulator(self.context, 'redis-urls')
        redis_urls = manipulator.get_literal_secrets_mapping()
        if self.secret_key not in redis_urls:
            count = len(redis_urls)
            manipulator.set_literal_secret(self.secret_key, 'redis://172.17.0.1:6379/{}'.format(count))
            kubernetes.install_global_secrets(self.context)

    @property
    def secret_key(self):
        return self.context['KUBE_SERVICE_NAME']

    def ensure_redis_running(self, redis_name):
        RedisRunningEnsurer(self.docker, redis_name).ensure()


class RedisRunningEnsurer(dependencies.ContainerRunningEnsurer):
    started_log = 'The server is now ready to accept connections'
    look_in_stream = 'out'

    def docker_run(self):
        self.docker('run', '-d', '--restart=always',
                    '--name={}'.format(self.name),
                    '-p', '172.17.0.1:6379:6379',
                    'redis:3.0.7')


class SetupDevCassandraCommand(BaseDevelCommand):
    custom_script_name = 'setup_dev_cassandra'

    def run_default(self):
        cassandra_name = self.context['DEV_CASSANDRA_NAME']
        keyspace_name = self.options.keyspace or self.context['KUBE_SERVICE_NAME']
        keyspace_name = self.clean_keyspace_name(keyspace_name)
        self.ensure_cassandra_running(cassandra_name)
        self.ensure_database_present(cassandra_name, keyspace_name)

    def clean_keyspace_name(self, original):
        cleaned = original.replace('-', '_')
        if cleaned != original:
            print("Keyspace name can't contain dashes (-), so it's been changed to: %s" % cleaned)
        return cleaned

    def ensure_cassandra_running(self, cassandra_name):
        CassandraRunningEnsurer(self.docker, cassandra_name).ensure()

    def ensure_database_present(self, cassandra_name, keyspace_name):
        query = ("create keyspace %s with replication = {'class': 'SimpleStrategy', "
                 "'replication_factor': 1}" % keyspace_name)
        try:
            self.docker('exec', cassandra_name, 'cqlsh', '-e', query)
        except sh.ErrorReturnCode as e:
            if b'already exists' not in e.stderr:
                raise e

    def get_parser(self):
        parser = super().get_parser()
        parser.add_argument('--keyspace', dest='keyspace', action='store',
                            default=None, help="used keyspace name")
        return parser


class CassandraRunningEnsurer(dependencies.ContainerRunningEnsurer):
    cassandra_version = '3.0.10'
    started_log = "Created default superuser role 'cassandra'"

    def docker_run(self):
        self.docker('run', '-d', '--restart=always', '--name={}'.format(self.name),
                    '-e', 'HEAP_NEWSIZE=1M', '-e', 'MAX_HEAP_SIZE=128M',
                    '-p', '172.17.0.1:9042:9042',
                    'cassandra:{}'.format(self.cassandra_version))


def build(args):
    print("Starting command build")
    cmd = BuildCommand(args)
    cmd.run()
    print("Done.")


def test(args):
    print("Starting command test")
    cmd = TestCommand(args)
    cmd.run()
    print("Done.")


def requirements(args):
    print("Starting command update requirements")
    cmd = UpdateRequirementsCommand(args)
    cmd.run()
    print("Done.")


def push(args):
    print("Starting command push")
    cmd = PushCommand(args)
    cmd.run()
    print("Done.")


def deploy(args):
    print("Starting command deploy")
    cmd = DeployCommand(args)
    cmd.run()
    print("Done.")


def setup_dev_db(args):
    print("Setting up dev db")
    cmd = SetupDevDbCommand(args)
    cmd.run()
    print("Done.")


def setup_dev_elastic(args):
    print("Setting up dev elasticsearch")
    cmd = SetupDevElasticsearchCommand(args)
    cmd.run()
    print("Done.")


def setup_pubsub_emulator(args):
    print("Setting up pubsub emulator")
    cmd = SetupPubSubEmulatorCommand(args)
    cmd.run()
    print("Done.")


def setup_dev_redis(args):
    print("Setting up dev redis")
    cmd = SetupDevRedisCommand(args)
    cmd.run()
    print("Done.")


def setup_dev_cassandra(args):
    print("Setting up dev cassandra")
    cmd = SetupDevCassandraCommand(args)
    cmd.run()
    print("Done.")
