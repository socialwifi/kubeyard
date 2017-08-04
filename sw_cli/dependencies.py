import contextlib

import sh


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
        try:
            container_status = str(self.docker_runner.run('inspect', '--format={{.State.Status}}', self.name)).strip()
        except sh.ErrorReturnCode:
            container_status = 'error'
        if container_status != 'running':
            with contextlib.suppress(sh.ErrorReturnCode):
                self.docker_runner.run('rm', '-fv', self.name)
            self.run_container()

    def run_container(self):
        print('running {}'.format(self.name))
        self.docker_run()
        for log in self.docker_runner.run('logs', '-f', self.name, _iter=self.look_in_stream):
            if self.started_log in log:
                break

    @property
    def started_log(self):
        raise NotImplementedError

    def docker_run(self):
        raise NotImplementedError
