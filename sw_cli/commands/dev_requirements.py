import sh

from sw_cli import dependencies
from sw_cli import kubernetes
from sw_cli.commands.devel import BaseDevelCommand

MAX_JOB_RETRIES = 10


class SetupDevDbCommand(BaseDevelCommand):
    """
    Command used in development. It should be called automatically from customized deploy script if microservice needs
    postgresql. By default it creates database KUBE_SERVICE_NAME (configured in context)
    available at 172.17.0.1:35432 by user postgres without password.
    """
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

    @classmethod
    def get_parser(cls, **kwargs):
        parser = super().get_parser(**kwargs)
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
    """
    Command used in development. It should be called automatically from customized deploy script if microservice needs
    elasticsearch. By default it creates elasticsearch container DEFAULT_DEV_ELASTIC_NAME (configured in context)
    available at 172.17.0.1:9200.
    """
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
    """
    Command used in development. It should be called automatically from customized deploy script if microservice needs
    google pub sub. By default it creates pubsub container DEV_PUBSUB_NAME (configured in context)
    available at 172.17.0.1:8042. It also creates topic and can create subscription. When used, support for pubsub
    emulator should be added to microservice.
    """
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

    @classmethod
    def get_parser(cls, **kwargs):
        parser = super().get_parser(**kwargs)
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
    """
    Command used in development. It should be called automatically from customized deploy script if microservice needs
    redis By default it creates redis container DEV_REDIS_NAME (configured in context)
    available at 172.17.0.1:6379. It also checks and updates if needed global secret redis-urls with next in order
    database.
    """
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
    """
    Command used in development. It should be called automatically from customized deploy script if microservice needs
    cassandra. By default it creates cassandra container DEV_CASSANDRA_NAME (configured in context)
    available at 172.17.0.1:9042.
    """
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

    @classmethod
    def get_parser(cls, **kwargs):
        parser = super().get_parser(**kwargs)
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
