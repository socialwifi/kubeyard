import logging
import time

import sh

logger = logging.getLogger(__name__)


def is_command_available(name):
    try:
        sh.bash('which', name)
    except sh.ErrorReturnCode:
        return False
    else:
        return True


class KubernetesDependency:
    def ensure_running(self):
        logger.debug('Checking if container "{}" is running...'.format(self.name))
        if self.is_container_running():
            logger.debug('"{}" is running'.format(self.name))
        else:
            logger.debug('Starting "{}"...'.format(self.name))
            self.run_container()
            logger.debug('"{}" started'.format(self.name))

    def run_container(self):
        self._apply_definition()
        self._wait_until_ready()
        self._wait_for_started_log()

    def _apply_definition(self):
        sh.kubectl('apply', '--record', '-f', self.definition)
        try:
            sh.kubectl('expose', '-f', self.definition)
        except sh.ErrorReturnCode_1 as e:
            if b'already exists' not in e.stderr:
                raise e
            else:
                logger.debug('Service for "{}" exists'.format(self.name))

    def _wait_until_ready(self):
        logger.debug('Waiting for "{}" to start (possibly downloading image)...'.format(self.name))
        ready = False
        while not ready:
            ready = self.is_container_running()
            if not ready:
                time.sleep(1)
        logger.debug('"{}" started'.format(self.name))

    def _wait_for_started_log(self):
        logger.debug('Waiting for started log for "{}"...'.format(self.name))
        for log in sh.kubectl('logs', '-f', self.pod_name, _iter='out'):
            if self.started_log in log:
                break
        logger.debug('Started log for "{}" found'.format(self.name))

    def is_container_running(self):
        try:
            container_ready = str(sh.kubectl(
                'get', 'pods',
                '--selector', self.selector,
                '--output', 'jsonpath="{.items[*].status.containerStatuses[*].ready}"'
            )).strip()
        except sh.ErrorReturnCode as e:
            logger.debug(e)
            return False
        else:
            return container_ready == '"true"'

    def run_command(self, *args):
        return sh.kubectl('exec', self.pod_name, '--', *args)

    @property
    def pod_name(self):
        return str(sh.kubectl(
            'get', 'pods',
            '--output', 'custom-columns=NAME:.metadata.name',
            '--no-headers',
            '--selector', self.selector
        )).strip()

    @property
    def selector(self):
        return 'app={}'.format(self.name)

    @property
    def started_log(self):
        raise NotImplementedError

    @property
    def name(self):
        raise NotImplementedError

    @property
    def definition(self):
        raise NotImplementedError
