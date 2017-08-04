import logging

import sh

from sw_cli import dependencies
from sw_cli import kubernetes
from sw_cli.commands.devel import DockerRunner

logger = logging.getLogger(__name__)

MAX_JOB_RETRIES = 10


class SetupDevBaseCommand:
    valid_arguments = ()

    def __init__(self, context: dict):
        self.context = context
        self.docker_runner = DockerRunner(context)

    def __call__(self, arguments: dict):
        if all(key in self.valid_arguments for key in arguments.keys()):
            self.run(arguments)
        else:
            logger.warning(
                'Requirement configuration is not valid: {}\n'
                'Available options are: {}'.format(arguments, self.valid_arguments))

    def run(self, arguments: dict):
        raise NotImplementedError


class SetupDevDbCommand(SetupDevBaseCommand):
    """
    Command used in development. It should be configured in sw_cli.yml if microservice needs
    postgresql. By default it creates database KUBE_SERVICE_NAME (configured in context)
    available at 172.17.0.1:35432 by user postgres without password.
    """
    valid_arguments = ('name')

    def run(self, arguments: dict):
        postgres_name = self.context['DEV_POSTGRES_NAME']
        database_name = arguments.get('name') or self.context['KUBE_SERVICE_NAME']
        self.ensure_postgres_running(postgres_name)
        self.ensure_database_present(postgres_name, database_name)

    def ensure_postgres_running(self, postgres_name):
        PostgresRunningEnsurer(self.docker_runner, postgres_name).ensure()

    def ensure_database_present(self, postgres_name, database_name):
        logger.debug('Ensuring that database "{}" exists...'.format(database_name))
        try:
            self.docker_runner.run('exec', postgres_name, 'createdb', database_name, '-U', 'postgres')
        except sh.ErrorReturnCode as e:
            if b'already exists' not in e.stderr:
                raise e
            else:
                logger.debug('Database "{}" exists'.format(database_name))
        else:
            logger.debug('Database "{}" created'.format(database_name))


class PostgresRunningEnsurer(dependencies.ContainerRunningEnsurer):
    postgres_version = '9.6.1'
    started_log = 'PostgreSQL init process complete; ready for start up.'

    def docker_run(self):
        self.docker_runner.run_with_output(
            'run', '-d', '--restart=always',
            '--name={}'.format(self.name),
            '-p', '172.17.0.1:35432:5432',
            'postgres:{}'.format(self.postgres_version))


class SetupDevElasticsearchCommand(SetupDevBaseCommand):
    """
    Command used in development. It should be configured in sw_cli.yml if microservice needs
    elasticsearch. By default it creates elasticsearch container DEFAULT_DEV_ELASTIC_NAME (configured in context)
    available at 172.17.0.1:9200.
    """
    valid_arguments = ()

    def run(self, arguments: dict):
        elastic_name = self.context['DEFAULT_DEV_ELASTIC_NAME']
        self.ensure_elastic_running(elastic_name)

    def ensure_elastic_running(self, elastic_name):
        ElasticsearchRunningEnsurer(self.docker_runner, elastic_name).ensure()


class ElasticsearchRunningEnsurer(dependencies.ContainerRunningEnsurer):
    elastic_version = '5.2.1'
    started_log = '] started'

    def docker_run(self):
        self.docker_runner.run_with_output(
            'run', '-d', '--restart=always',
            '--name={}'.format(self.name),
            '-e', 'ES_JAVA_OPTS=-Xms200m -Xmx200m',
            '-p', '172.17.0.1:9300:9300',
            '-p', '172.17.0.1:9200:9200',
            'elasticsearch:{}'.format(self.elastic_version))


class SetupPubSubEmulatorCommand(SetupDevBaseCommand):
    """
    Command used in development. It should be configured in sw_cli.yml if microservice needs
    google pub sub. By default it creates pubsub container DEV_PUBSUB_NAME (configured in context)
    available at 172.17.0.1:8042. It also creates topic and can create subscription. When used, support for pubsub
    emulator should be added to microservice.
    """
    valid_arguments = ('topic', 'subscription')

    def run(self, arguments: dict):
        pubsub_name = self.context['DEV_PUBSUB_NAME']
        topic_name = arguments.get('topic') or self.context['KUBE_SERVICE_NAME']
        self.ensure_pubsub_running(pubsub_name)
        self.ensure_topic_present(pubsub_name, topic_name)
        try:
            subscription_name = arguments['subscription']
        except KeyError:
            logger.debug("Subscription not specified, it won't be created")
        else:
            self.ensure_subscription_present(pubsub_name, topic_name, subscription_name)

    def ensure_pubsub_running(self, pubsub_name):
        PubSubRunningEnsurer(self.docker_runner, pubsub_name).ensure()

    def ensure_topic_present(self, pubsub_name, topic_name):
        logger.debug('Ensuring that topic "{}" exists...'.format(topic_name))
        try:
            self.docker_runner.run('exec', pubsub_name, 'pubsub_add_topic', topic_name)
        except sh.ErrorReturnCode as e:
            if b'Topic already exists' not in e.stderr:
                raise
            else:
                logger.debug('Topic "{}" exists'.format(topic_name))
        else:
            logger.debug('Topic "{}" created'.format(topic_name))

    def ensure_subscription_present(self, pubsub_name, topic_name, subscription_name):
        logger.debug('Ensuring that subscription "{}" exists...'.format(subscription_name))
        try:
            self.docker_runner.run('exec', pubsub_name, 'pubsub_add_subscription', topic_name, subscription_name)
        except sh.ErrorReturnCode as e:
            if b'Subscription already exists' not in e.stderr:
                raise
            else:
                logger.debug('Subscription "{}" exists'.format(subscription_name))
        else:
            logger.debug('Subscription "{}" created'.format(subscription_name))


class PubSubRunningEnsurer(dependencies.ContainerRunningEnsurer):
    started_log = '[pubsub] INFO: Server started, listening on'
    look_in_stream = 'err'

    def docker_run(self):
        self.docker_runner.run_with_output(
            'run', '-d', '--restart=always',
            '--name={}'.format(self.name),
            '-p', '172.17.0.1:8042:8042',
            'docker.socialwifi.com/sw-pubsub-emulator-helper')


class SetupDevRedisCommand(SetupDevBaseCommand):
    """
    Command used in development. It should be configured in sw_cli.yml if microservice needs
    redis By default it creates redis container DEV_REDIS_NAME (configured in context)
    available at 172.17.0.1:6379. It also checks and updates if needed global secret redis-urls with next in order
    database.
    """
    valid_arguments = ()

    def run(self, arguments: dict):
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
        RedisRunningEnsurer(self.docker_runner, redis_name).ensure()


class RedisRunningEnsurer(dependencies.ContainerRunningEnsurer):
    started_log = 'The server is now ready to accept connections'
    look_in_stream = 'out'

    def docker_run(self):
        self.docker_runner.run_with_output(
            'run', '-d', '--restart=always',
            '--name={}'.format(self.name),
            '-p', '172.17.0.1:6379:6379',
            'redis:3.0.7')


class SetupDevCassandraCommand(SetupDevBaseCommand):
    """
    Command used in development. It should be configured in sw_cli.yml if microservice needs
    cassandra. By default it creates cassandra container DEV_CASSANDRA_NAME (configured in context)
    available at 172.17.0.1:9042.
    """
    valid_arguments = ('keyspace')

    def run(self, arguments: dict):
        cassandra_name = self.context['DEV_CASSANDRA_NAME']
        keyspace_name = arguments.get('keyspace') or self.context['KUBE_SERVICE_NAME']
        keyspace_name = self.clean_keyspace_name(keyspace_name)
        self.ensure_cassandra_running(cassandra_name)
        self.ensure_database_present(cassandra_name, keyspace_name)

    def clean_keyspace_name(self, original):
        cleaned = original.replace('-', '_')
        if cleaned != original:
            logger.warning("Keyspace name can't contain dashes (-), so it's been changed to: %s" % cleaned)
        return cleaned

    def ensure_cassandra_running(self, cassandra_name):
        CassandraRunningEnsurer(self.docker_runner, cassandra_name).ensure()

    def ensure_database_present(self, cassandra_name, keyspace_name):
        logger.debug('Ensuring that keyspace "{}" exists...'.format(keyspace_name))
        query = ("create keyspace %s with replication = {'class': 'SimpleStrategy', "
                 "'replication_factor': 1}" % keyspace_name)
        try:
            self.docker_runner.run('exec', cassandra_name, 'cqlsh', '-e', query)
        except sh.ErrorReturnCode as e:
            if b'already exists' not in e.stderr:
                raise e
            else:
                logger.debug('Keyspace "{}" exists'.format(keyspace_name))
        else:
            logger.debug('Keyspace "{}" created'.format(keyspace_name))


class CassandraRunningEnsurer(dependencies.ContainerRunningEnsurer):
    cassandra_version = '3.0.10'
    started_log = "Created default superuser role 'cassandra'"

    def docker_run(self):
        self.docker_runner.run_with_output(
            'run', '-d', '--restart=always', '--name={}'.format(self.name),
            '-e', 'HEAP_NEWSIZE=1M', '-e', 'MAX_HEAP_SIZE=128M',
            '-p', '172.17.0.1:9042:9042',
            'cassandra:{}'.format(self.cassandra_version))


class SetupDevCommandDispatcher:
    commands = {
        'postgres': SetupDevDbCommand,
        'redis': SetupDevRedisCommand,
        'elastic': SetupDevElasticsearchCommand,
        'pubsub': SetupPubSubEmulatorCommand,
        'cassandra': SetupDevCassandraCommand,
    }

    def __init__(self, context: dict):
        self.context = context

    def dispatch_all(self, requirements: dict):
        for requirement in requirements:
            if 'kind' in requirement:
                self.dispatch(requirement)
            else:
                logger.warning("Skipping requirement without specified kind. Requirement: {}".format(requirement))

    def dispatch(self, requirement: dict):
        arguments = requirement.copy()
        kind = arguments.pop('kind')
        logger.info('Checking requirement of kind "{}"...'.format(kind))
        try:
            command = self.commands[kind](self.context)
        except KeyError:
            logger.warning('Kind "{}" is not supported!'.format(kind))
        else:
            command(arguments)
            logger.info('Requirement of kind "{}" satisfied'.format(kind))
