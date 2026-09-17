import logging
import pathlib

import sh

from kubeyard import dependencies
from kubeyard import kubernetes

logger = logging.getLogger(__name__)
definitions_directory = pathlib.Path(__file__).parent.parent / 'definitions' / 'dev_requirements'


class Requirement:
    valid_arguments = ()
    dependency_class = None

    def __init__(self, context: dict):
        self.context = context
        self.namespace = context.get('KUBEYARD_NAMESPACE', '')

    def __call__(self, arguments: dict):
        if all(key in self.valid_arguments for key in arguments.keys()):
            return self.run(arguments)
        else:
            logger.warning(
                'Requirement configuration is not valid: {}\n'
                'Available options are: {}'.format(arguments, self.valid_arguments))
            return False

    def run(self, arguments: dict):
        raise NotImplementedError


class PostgresDependency(dependencies.KubernetesDependency):
    name = 'dev-postgres'
    definition = definitions_directory / 'postgres.yaml'
    started_log = 'PostgreSQL init process complete; ready for start up.'

    def ensure_database_present(self, database_name) -> bool:
        logger.debug('Ensuring that database "{}" exists...'.format(database_name))
        try:
            self.run_command('createdb', database_name, '-U', 'postgres')
        except sh.ErrorReturnCode as e:
            if b'already exists' not in e.stderr:
                raise e
            else:
                logger.debug('Database "{}" exists'.format(database_name))
                return False
        else:
            logger.debug('Database "{}" created'.format(database_name))
            return True


class Postgres(Requirement):
    valid_arguments = ('name')
    dependency_class = PostgresDependency

    def run(self, arguments: dict):
        database_name = arguments.get('name') or self.context['KUBE_SERVICE_NAME']
        dependency = self.dependency_class(self.namespace)
        dependency.ensure_running()
        return dependency.ensure_database_present(database_name)


class CockroachDBDependency(dependencies.KubernetesDependency):
    name = 'dev-cockroachdb'
    definition = definitions_directory / 'cockroachdb.yaml'
    started_log = 'CockroachDB node starting'

    def ensure_database_present(self, database_name) -> bool:
        logger.debug('Ensuring that database "{}" exists...'.format(database_name))
        try:
            self.run_command('/cockroach/cockroach', 'sql', '--insecure',
                             '-e', 'CREATE DATABASE "{}";'.format(database_name))
        except sh.ErrorReturnCode as e:
            if b'already exists' not in e.stderr:
                raise e
            else:
                logger.debug('Database "{}" exists'.format(database_name))
                return False
        else:
            logger.debug('Database "{}" created'.format(database_name))
            return True


class CockroachDB(Requirement):
    valid_arguments = ('name',)
    dependency_class = CockroachDBDependency

    def run(self, arguments: dict):
        database_name = arguments.get('name') or self.context['KUBE_SERVICE_NAME']
        dependency = self.dependency_class(self.namespace)
        dependency.ensure_running()
        return dependency.ensure_database_present(database_name)


class ElasticsearchDependency(dependencies.KubernetesDependency):
    name = 'dev-elasticsearch'
    definition = definitions_directory / 'elasticsearch.yaml'
    started_log = '] started'


class Elasticsearch(Requirement):
    valid_arguments = ()
    dependency_class = ElasticsearchDependency

    def run(self, arguments: dict):
        self.ensure_elastic_running()
        return False

    def ensure_elastic_running(self):
        self.dependency_class(self.namespace).ensure_running()


class PubSubDependency(dependencies.KubernetesDependency):
    name = 'dev-pubsub'
    definition = definitions_directory / 'pubsub-emulator.yaml'
    started_log = '[pubsub] INFO: Server started, listening on'

    def ensure_topic_present(self, topic_name):
        logger.debug('Ensuring that topic "{}" exists...'.format(topic_name))
        try:
            self.run_command('pubsub_add_topic', topic_name)
        except sh.ErrorReturnCode as e:
            if b'Topic already exists' not in e.stderr:
                raise
            else:
                logger.debug('Topic "{}" exists'.format(topic_name))
        else:
            logger.debug('Topic "{}" created'.format(topic_name))

    def ensure_subscription_present(self, topic_name, subscription_name):
        logger.debug('Ensuring that subscription "{}" exists...'.format(subscription_name))
        try:
            self.run_command('pubsub_add_subscription', topic_name, subscription_name)
        except sh.ErrorReturnCode as e:
            if b'Subscription already exists' not in e.stderr:
                raise
            else:
                logger.debug('Subscription "{}" exists'.format(subscription_name))
        else:
            logger.debug('Subscription "{}" created'.format(subscription_name))


class PubSubEmulator(Requirement):
    valid_arguments = ('topic', 'subscription')
    dependency_class = PubSubDependency

    def run(self, arguments: dict):
        topic_name = arguments.get('topic') or self.context['KUBE_SERVICE_NAME']
        dependency = self.dependency_class(self.namespace)
        dependency.ensure_running()
        dependency.ensure_topic_present(topic_name)
        try:
            subscription_name = arguments['subscription']
        except KeyError:
            logger.debug("Subscription not specified, it won't be created")
        else:
            dependency.ensure_subscription_present(topic_name, subscription_name)
        return False


class RedisDependency(dependencies.KubernetesDependency):
    name = 'dev-redis'
    definition = definitions_directory / 'redis.yaml'
    started_log = 'The server is now ready to accept connections'


class Redis(Requirement):
    valid_arguments = ('name', )
    dependency_class = RedisDependency
    secret_name = 'redis-urls'

    def run(self, arguments: dict):
        dependency = self.dependency_class(self.namespace)
        dependency.ensure_running()
        secret_key = arguments.get('name') or self.context['KUBE_SERVICE_NAME']
        secrets_manipulator = kubernetes.get_global_secrets_manipulator(self.context, self.secret_name)
        self.ensure_secret_is_present_in_file(secrets_manipulator, secret_key, redis_host=dependency.name)
        self.ensure_secret_is_installed(secrets_manipulator, secret_key)
        return False

    def ensure_secret_is_present_in_file(self, secrets_manipulator, secret_key, redis_host):
        logger.debug('Ensuring that secret key "{}" is present in file...'.format(secret_key))
        redis_urls = secrets_manipulator.get_literal_secrets_mapping()
        if secret_key in redis_urls:
            logger.debug('Secret key is already present in file')
        else:
            count = len(redis_urls)
            secrets_manipulator.set_literal_secret(
                key=secret_key, value='redis://{}:6379/{}'.format(redis_host, count))
            logger.debug('Secret key added to file')

    def ensure_secret_is_installed(self, secrets_manipulator, secret_key):
        logger.debug('Ensuring that secret key "{}" is present in secret "{}"...'.format(secret_key, self.secret_name))
        if secrets_manipulator.is_key_present(secret_key):
            logger.debug('Secret key is already present in secret')
        else:
            kubernetes.install_global_secrets(self.context)
            logger.debug('Secret key added to secret')


class CassandraDependency(dependencies.KubernetesDependency):
    name = 'dev-cassandra'
    definition = definitions_directory / 'cassandra.yaml'
    started_log = "Created default superuser role 'cassandra'"

    def ensure_database_present(self, keyspace_name):
        keyspace_name = self.clean_keyspace_name(keyspace_name)
        logger.debug('Ensuring that keyspace "{}" exists...'.format(keyspace_name))
        query = ("create keyspace %s with replication = {'class': 'SimpleStrategy', "
                 "'replication_factor': 1}" % keyspace_name)
        try:
            self.run_command('cqlsh', '-e', query)
        except sh.ErrorReturnCode as e:
            if b'already exists' not in e.stderr:
                raise e
            else:
                logger.debug('Keyspace "{}" exists'.format(keyspace_name))
        else:
            logger.debug('Keyspace "{}" created'.format(keyspace_name))

    def clean_keyspace_name(self, original):
        cleaned = original.replace('-', '_')
        if cleaned != original:
            logger.warning("Keyspace name can't contain dashes (-), so it's been changed to: %s" % cleaned)
        return cleaned


class Cassandra(Requirement):
    valid_arguments = ('keyspace')
    dependency_class = CassandraDependency

    def run(self, arguments: dict):
        keyspace_name = arguments.get('keyspace') or self.context['KUBE_SERVICE_NAME']
        dependency = self.dependency_class(self.namespace)
        dependency.ensure_running()
        dependency.ensure_database_present(keyspace_name)
        return False


class RabbitMQDependency(dependencies.KubernetesDependency):
    name = 'dev-rabbitmq'
    definition = definitions_directory / 'rabbitmq.yaml'
    started_log = 'Starting RabbitMQ'


class RabbitMQ(Requirement):
    valid_arguments = ()
    dependency_class = RabbitMQDependency

    def run(self, arguments: dict):
        dependency = self.dependency_class(self.namespace)
        dependency.ensure_running()
        return False


class RequirementsDispatcher:
    commands = {
        'postgres': Postgres,
        'cockroachdb': CockroachDB,
        'redis': Redis,
        'elastic': Elasticsearch,
        'pubsub': PubSubEmulator,
        'cassandra': Cassandra,
        'rabbitmq': RabbitMQ,
    }

    def __init__(self, context: dict):
        self.context = context

    def dispatch_all(self, requirements: dict) -> bool:
        created_database = False
        for requirement in requirements:
            if 'kind' in requirement:
                created_database = self.dispatch(requirement) or created_database
            else:
                logger.warning("Skipping requirement without specified kind. Requirement: {}".format(requirement))
        return created_database

    def dispatch(self, requirement: dict) -> bool:
        arguments = requirement.copy()
        kind = arguments.pop('kind')
        logger.info('Checking requirement of kind "{}"...'.format(kind))
        try:
            command = self.commands[kind](self.context)
        except KeyError:
            logger.warning('Kind "{}" is not supported!'.format(kind))
            return False
        else:
            created_database = command(arguments)
            logger.info('Requirement of kind "{}" satisfied'.format(kind))
            return bool(created_database)


def provided_service_names() -> set:
    """
    Names of the Services kubeyard provisions itself, once per namespace.

    Derived from the requirement registry rather than listed literally, so a
    requirement added to RequirementsDispatcher.commands cannot leave this
    stale. Used by kubeyard.aliases to keep a workspace from aliasing away the
    very dependencies it runs its own copies of.
    """
    return {
        requirement_class.dependency_class.name
        for requirement_class in RequirementsDispatcher.commands.values()
    }
