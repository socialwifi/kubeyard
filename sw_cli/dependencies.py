import contextlib
import logging

import sh


logger = logging.getLogger(__name__)


def is_command_available(name):
    try:
        sh.bash('which', name)
    except sh.ErrorReturnCode:
        return False
    else:
        return True


class ContainerRunningEnsurer:
    look_in_stream = 'out'

    def __init__(self, docker_runner, name):
        self.docker_runner = docker_runner
        self.name = name

    def ensure(self):
        logger.info('Checking if container "{}" is running...'.format(self.name))
        try:
            container_status = str(self.docker_runner.run('inspect', '--format={{.State.Status}}', self.name)).strip()
        except sh.ErrorReturnCode:
            container_status = 'error'
        if container_status == 'running':
            logger.info('{} is running'.format(self.name))
        else:
            with contextlib.suppress(sh.ErrorReturnCode):
                self.docker_runner.run('rm', '-fv', self.name)
            logger.info('Starting {}...'.format(self.name))
            self.run_container()
            logger.info('{} started'.format(self.name))

    def run_container(self):
        self.docker_run()
        logger.info('Waiting for {} to start...'.format(self.name))
        for log in self.docker_runner.run('logs', '-f', self.name, _iter=self.look_in_stream):
            if self.started_log in log:
                break

    @property
    def started_log(self):
        raise NotImplementedError

    def docker_run(self):
        raise NotImplementedError
