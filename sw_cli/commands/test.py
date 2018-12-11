import abc
import json
import logging
import sys
import typing

import sh

from sw_cli import base_command
from sw_cli.commands.devel import BaseDevelCommand

logger = logging.getLogger(__name__)


class TestCommand(BaseDevelCommand):
    """
    Runs tests in docker image built by build command. Can be overridden in <project_dir>/sripts/test.

    **IMPORTANT** for now only Postgres database is supported.
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
        self.context['HOST_VOLUMES'] = ' '.join(self.volumes)

    @property
    def args(self) -> list:
        return list(self.test_options)

    @property
    def volumes(self) -> typing.Iterable[str]:
        if self.is_development:
            mounted_project_dir = self.cluster.get_mounted_project_dir(self.project_dir)
            for volume in self.context.get('DEV_MOUNTED_PATHS', []):
                if 'mount-in-tests' in volume and volume['mount-in-tests']['image-name'] == self.image_name:
                    host_path = str(mounted_project_dir / volume['host-path'])
                    container_path = volume['mount-in-tests']['path']
                    mount_mode = self.get_mount_mode(volume['mount-in-tests'])
                    yield from ['-v', '{}:{}:{}'.format(host_path, container_path, mount_mode)]

    def get_mount_mode(self, configuration):
        mount_mode = configuration.get('mount-mode', 'ro')
        if mount_mode not in {'ro', 'rw'}:
            raise base_command.CommandException('Volume "mount-mode" should be one of: "ro", "rw".')
        return mount_mode

    def run_default(self):
        if self.context.get('TESTS_WITH_DATABASE'):
            database_class = DATABASE_MAP[self.context.get("TEST_DATABASE_TYPE", "postgres")]
            with database_class(
                    is_development=self.is_development,
                    volumes=self.volumes,
                    context=self.context, tag=self.tag,
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
            sh.docker.run.bake(
                rm=True,
                _out=sys.stdout.buffer,
                _err=sys.stdout.buffer,
                net=database.network if database else 'none',
            )(
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
            context: dict, tag: str,
            tested_image_name: str,
            force_recreate: bool = False,
            force_migrate: bool = False,
    ):
        self.is_development = is_development
        self.volumes = volumes
        self.context = context
        self.tag = tag
        self.tested_image_name = tested_image_name
        self.force_migrate = force_migrate
        self.force_recreate = force_recreate
        self._migrated = False

    def __enter__(self):
        if not self.is_development or self.force_recreate:
            self.remove_database()
        if self.container_stopped:
            logger.info("Found stopped DB, restarting it!")
            sh.docker.start(self.container_name)
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
            container_info = json.loads(str(sh.docker.inspect(self.container_name)))
        except sh.ErrorReturnCode_1:
            return False
        else:
            return container_info[0]['State']['Running'] is False

    @property
    def already_up(self) -> bool:
        try:
            sh.docker.inspect(self.container_name)
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
            sh.docker.rm.bake(
                force=True,
                volumes=True,
            )(
                self.container_name,
            )
        except sh.ErrorReturnCode_1 as e:
            logger.info('Database does not exist yet.')
            logger.debug(e)

    @abc.abstractmethod
    def create(self):
        raise NotImplementedError

    def wait_until_ready(self):
        logger.info('Waiting for database...')
        for log in sh.docker.logs.bake(follow=True, _err_to_out=True, _iter='out')(self.container_name):
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
            sh.docker.run.bake(
                net=self.network,
                rm=True,
                _err_to_out=True,
            )(
                *self.volumes,
                self.tested_image_name,
                self.context['TEST_MIGRATION_COMMAND'],
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
        sh.docker.run.bake(
            restart='always',
            net='none',
            name=self.container_name,
            detach=True,
            e='POSTGRES_DB={}'.format(self.context['TEST_DATABASE_NAME']),
        )(
            self.context['TEST_DATABASE_IMAGE'],
        )


class CockroachDatabase(Database):
    started_log = 'initialized new cluster'

    def create(self):
        logger.info('Releasing cockroaches...')
        sh.docker.run.bake(
            restart='always',
            net='none',
            name=self.container_name,
            detach=True,
        )(
            self.context['TEST_DATABASE_IMAGE'],
            'start',
            '--insecure',
            '--host=localhost',
            '--logtostderr',
        )
        self._create_database()

    def _create_database(self):
        self.wait_until_ready()
        sh.docker.run.bake(
            net=self.network,
            rm=True,
        )(
            self.context["TEST_DATABASE_IMAGE"],
            "sql",
            "--insecure",
            "-e",
            "CREATE DATABASE {}".format(self.context['TEST_DATABASE_NAME']),
        )


DATABASE_MAP = {
    'postgres': PostgresDatabase,
    'cockroach': CockroachDatabase,
}
