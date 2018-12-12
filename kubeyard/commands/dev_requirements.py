import logging
import pathlib

import sh

from kubeyard import dependencies
from kubeyard import kubernetes

logger = logging.getLogger(__name__)
definitions_directory = pathlib.Path(__file__).parent.parent / 'definitions' / 'dev_requirements'


class Requirement:
    valid_arguments = ()

    def __init__(self, context: dict):
        self.context = context

    def __call__(self, arguments: dict):
        if all(key in self.valid_arguments for key in arguments.keys()):
            self.run(arguments)
        else:
            logger.warning(
                'Requirement configuration is not valid: {}\n'
                'Available options are: {}'.format(arguments, self.valid_arguments))

    def run(self, arguments: dict):
        raise NotImplementedError


class Postgres(Requirement):
    valid_arguments = ('name')

    def run(self, arguments: dict):
        database_name = arguments.get('name') or self.context['KUBE_SERVICE_NAME']
        dependency = PostgresDependency()
        dependency.ensure_running()
        dependency.ensure_database_present(database_name)


class PostgresDependency(dependencies.KubernetesDependency):
    name = 'dev-postgres'
    definition = definitions_directory / 'postgres.yaml'
    started_log = 'PostgreSQL init process complete; ready for start up.'

    def ensure_database_present(self, database_name):
        logger.debug('Ensuring that database "{}" exists...'.format(database_name))
        try:
            self.run_command('createdb', database_name, '-U', 'postgres')
        except sh.ErrorReturnCode as e:
            if b'already exists' not in e.stderr:
                raise e
            else:
                logger.debug('Database "{}" exists'.format(database_name))
        else:
            logger.debug('Database "{}" created'.format(database_name))


class CockroachDB(Requirement):
    valid_arguments = ('name',)

    def run(self, arguments: dict):
        database_name = arguments.get('name') or self.context['KUBE_SERVICE_NAME']
        dependency = CockroachDBDependency()
        dependency.ensure_running()
        dependency.ensure_database_present(database_name)


class CockroachDBDependency(dependencies.KubernetesDependency):
    name = 'dev-cockroachdb'
    definition = definitions_directory / 'cockroachdb.yaml'
    started_log = 'CockroachDB node starting'

    def ensure_database_present(self, database_name):
        logger.debug('Ensuring that database "{}" exists...'.format(database_name))
        try:
            self.run_command('/cockroach/cockroach', 'sql', '--insecure',
                             '-e', 'CREATE DATABASE "{}";'.format(database_name))
        except sh.ErrorReturnCode as e:
            if b'already exists' not in e.stderr:
                raise e
            else:
                logger.debug('Database "{}" exists'.format(database_name))
        else:
            logger.debug('Database "{}" created'.format(database_name))


class Elasticsearch(Requirement):
    valid_arguments = ()

    def run(self, arguments: dict):
        self.ensure_elastic_running()

    def ensure_elastic_running(self):
        ElasticsearchDependency().ensure_running()


class ElasticsearchDependency(dependencies.KubernetesDependency):
    name = 'dev-elasticsearch'
    definition = definitions_directory / 'elasticsearch.yaml'
    started_log = '] started'


class PubSubEmulator(Requirement):
    valid_arguments = ('topic', 'subscription')

    def run(self, arguments: dict):
        topic_name = arguments.get('topic') or self.context['KUBE_SERVICE_NAME']
        dependency = PubSubDependency()
        dependency.ensure_running()
        dependency.ensure_topic_present(topic_name)
        try:
            subscription_name = arguments['subscription']
        except KeyError:
            logger.debug("Subscription not specified, it won't be created")
        else:
            dependency.ensure_subscription_present(topic_name, subscription_name)


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


class Redis(Requirement):
    valid_arguments = ('name', )
    secret_name = 'redis-urls'

    def run(self, arguments: dict):
        dependency = RedisDependency()
        dependency.ensure_running()
        secret_key = arguments.get('name') or self.context['KUBE_SERVICE_NAME']
        secrets_manipulator = kubernetes.get_global_secrets_manipulator(self.context, self.secret_name)
        self.ensure_secret_is_present_in_file(secrets_manipulator, secret_key, redis_host=dependency.name)
        self.ensure_secret_is_installed(secrets_manipulator, secret_key)

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


class RedisDependency(dependencies.KubernetesDependency):
    name = 'dev-redis'
    definition = definitions_directory / 'redis.yaml'
    started_log = 'The server is now ready to accept connections'


class Cassandra(Requirement):
    valid_arguments = ('keyspace')

    def run(self, arguments: dict):
        keyspace_name = arguments.get('keyspace') or self.context['KUBE_SERVICE_NAME']
        dependency = CassandraDependency()
        dependency.ensure_running()
        dependency.ensure_database_present(keyspace_name)


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


class RequirementsDispatcher:
    commands = {
        'postgres': Postgres,
        'cockroachdb': CockroachDB,
        'redis': Redis,
        'elastic': Elasticsearch,
        'pubsub': PubSubEmulator,
        'cassandra': Cassandra,
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
