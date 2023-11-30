import abc
import json
import logging
import sys
import typing

import sh

from kubeyard.commands.devel import BaseDevelCommand
from kubeyard.commands.devel import DockerRunner

logger = logging.getLogger(__name__)


class TestCommand(BaseDevelCommand):
    """
    Runs tests in docker image built by build command. Can be overridden in <project_dir>/sripts/test.

    Supported databases:
        - Postgres
        - CockroachDB
    You can override migration command and test command passed to docker container with code.

    \b
    Example:
    test_migration_command: migrate_user
    test_command: db_tests_for_user

    If kubeyard is set up in development mode it uses minikube as docker host and mounts volumes configured in
    dev_mounted_paths in config/kubeyard.yml if they have mount-in-test set.

    \b
    Example:
    dev_mounted_paths:
    - name: dev-volume
      host-path: docker/source
      mount-in-tests:
        path: /package
        image-name: sw-project


    You can setup database before tests
    (on dev environment db will be cached, otherwise it will be removed immediately after tests).

    \b
    Example:
    tests_with_database: true
    test_database_type: postgres <- Available types: `postgres`, `cockroach`. `postgres` is default.
    test_database_image: postgres:10.3
    test_database_name: test

    """
    custom_script_name = 'test'
    context_vars = ["force_recreate_database", "force_migrate_database"]

    def __init__(self, *, force_recreate_database, force_migrate_database, test_options, **kwargs):
        super().__init__(**kwargs)
        self.test_options = test_options
        self.force_recreate_database = force_recreate_database
        self.force_migrate_database = force_migrate_database

    @property
    def args(self) -> list:
        return list(self.test_options)

    def run_default(self):
        if self.context.get('TESTS_WITH_DATABASE'):
            database_class = DATABASE_MAP[self.context.get("TEST_DATABASE_TYPE", "postgres")]
            with database_class(
                    is_development=self.is_development,
                    volumes=self.volumes,
                    context=self.context,
                    tag=self.tag,
                    docker_runner=self.docker_runner,
                    tested_image_name=self.image,
                    force_recreate=self.force_recreate_database,
                    force_migrate=self.force_migrate_database,
            ) as database:
                self.run_tests(database)
        else:
            self.run_tests()

    def run_tests(self, database: 'Database' = None):
        logger.info('Running tests...')
        try:
            self.docker_runner.run_with_output(
                'run',
                '--rm',
                '--init',
                '--net={}'.format(database.network if database else 'none'),
                *self.volumes,
                self.image,
                self.context['TEST_COMMAND'],
                *self.test_options,
            )
        except sh.ErrorReturnCode_1 as e:
            logger.debug(e)
            sys.exit(1)


class Database(metaclass=abc.ABCMeta):
    def __init__(
            self,
            is_development: bool,
            volumes: typing.Iterable[str],
            context: dict,
            tag: str,
            docker_runner: DockerRunner,
            tested_image_name: str,
            force_recreate: bool = False,
            force_migrate: bool = False,
    ):
        self.is_development = is_development
        self.volumes = volumes
        self.context = context
        self.tag = tag
        self.docker_runner = docker_runner
        self.tested_image_name = tested_image_name
        self.force_migrate = force_migrate
        self.force_recreate = force_recreate
        self._migrated = False

    def __enter__(self):
        if not self.is_development or self.force_recreate:
            self.remove_database()
        if self.container_stopped:
            logger.info("Found stopped DB, restarting it!")
            self.docker_runner.run('start', self.container_name)
        if not self.already_up:
            self.create()
            self.wait_until_ready()
            self.migrate()
        if self.force_migrate:
            self.migrate()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self.is_development:
            self.remove_database()

    @property
    def container_stopped(self) -> bool:
        try:
            container_info = json.loads(str(self.docker_runner.run('inspect', self.container_name)))
        except sh.ErrorReturnCode_1:
            return False
        else:
            return container_info[0]['State']['Running'] is False

    @property
    def already_up(self) -> bool:
        try:
            self.docker_runner.run('inspect', self.container_name)
            return True
        except sh.ErrorReturnCode_1:
            return False

    @property
    def container_name(self) -> str:
        image_name = self.context['DOCKER_IMAGE_NAME']
        return f'db-test-{image_name}-{self.tag}'

    def remove_database(self):
        logger.info('Removing database...')
        try:
            self.docker_runner.run('rm', '--force', '--volumes', self.container_name)
        except sh.ErrorReturnCode_1 as e:
            logger.info('Database does not exist yet.')
            logger.debug(e)

    @abc.abstractmethod
    def create(self):
        raise NotImplementedError

    def wait_until_ready(self):
        logger.info('Waiting for database...')
        for log in self.docker_runner.run('logs', '--follow', self.container_name, _err_to_out=True, _iter='out'):
            if self.started_log in log:
                logger.info('Database ready!')
                break

    @property
    @abc.abstractmethod
    def started_log(self):
        raise NotImplementedError

    def migrate(self):
        if not self._migrated:
            logger.info('Running migrations...')
            self.docker_runner.run(
                'run',
                '--net', self.network,
                '--rm',
                *self.volumes,
                self.tested_image_name,
                self.context['TEST_MIGRATION_COMMAND'],
                _err_to_out=True,
            )
            logger.info('Migrations done!')
        self._migrated = True

    @property
    def network(self) -> str:
        return f'container:{self.container_name}'


class PostgresDatabase(Database):
    started_log = 'PostgreSQL init process complete; ready for start up.'

    def create(self):
        logger.info('Setting up database...')
        self.docker_runner.run(
            'run',
            '--restart', 'always',
            '--net', 'none',
            '--name', self.container_name,
            '--detach',
            '-e', 'POSTGRES_DB={}'.format(self.context['TEST_DATABASE_NAME']),
            self.context['TEST_DATABASE_IMAGE'],
        )


class CockroachDatabase(Database):
    started_log = 'initialized new cluster'

    def create(self):
        logger.info('Releasing cockroaches...')
        self.docker_runner.run(
            'run',
            '--restart', 'always',
            '--net', 'none',
            '--name', self.container_name,
            '--detach',
            self.context['TEST_DATABASE_IMAGE'],
            'start-single-node',
            '--insecure',
            '--host=localhost',
            '--logtostderr',
        )
        self._create_database()

    def _create_database(self):
        self.wait_until_ready()
        self.docker_runner.run(
            'run',
            '--net', self.network,
            '--rm',
            self.context['TEST_DATABASE_IMAGE'],
            'sql',
            '--insecure',
            '-e',
            'CREATE DATABASE {}'.format(self.context['TEST_DATABASE_NAME']),
        )


DATABASE_MAP = {
    'postgres': PostgresDatabase,
    'cockroach': CockroachDatabase,
}
