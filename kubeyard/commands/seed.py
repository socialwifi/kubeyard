import logging
import shlex
import sys

import sh

from kubeyard import base_command
from kubeyard import kubectl as kubectl_helper

logger = logging.getLogger(__name__)

ROLLOUT_TIMEOUT = '180s'


class SeedError(Exception):
    pass


def select_pod(pod_names, wanted) -> str:
    pod_names = list(pod_names)
    if wanted in pod_names:
        return wanted
    candidates = sorted((name for name in pod_names if name.startswith(wanted)), key=len)
    if not candidates:
        raise SeedError(
            'No pod matching {!r} found. Available pods: {}'.format(wanted, ', '.join(pod_names) or 'none'))
    if len(candidates) > 1:
        logger.warning('More than one pod matches {!r}; using "{}".'.format(wanted, candidates[0]))
    return candidates[0]


class SeedRunner:
    def __init__(self, context):
        self.context = context

    @property
    def namespace_args(self):
        return kubectl_helper.namespace_args(self.context.get('KUBEYARD_NAMESPACE', ''))

    @property
    def target(self) -> str:
        return self.context.get('DEV_SEED_POD') or self.context['KUBE_SERVICE_NAME']

    @property
    def command(self) -> list:
        return shlex.split(self.context['DEV_SEED_COMMAND'])

    def wait_for_rollout(self, deployment_names):
        for name in deployment_names:
            logger.info('Waiting for deployment "{}" to be ready...'.format(name))
            try:
                sh.kubectl('rollout', 'status', 'deployment/{}'.format(name),
                           *self.namespace_args, '--timeout', ROLLOUT_TIMEOUT,
                           _out=sys.stdout.buffer, _err=sys.stdout.buffer)
            except sh.ErrorReturnCode as e:
                raise SeedError(
                    'Deployment "{}" did not become ready within {}: {}'.format(
                        name, ROLLOUT_TIMEOUT, e)) from e

    def pod_names(self):
        output = str(sh.kubectl(
            'get', 'pods', *self.namespace_args,
            '--field-selector', 'status.phase=Running',
            '--output', 'jsonpath={.items[*].metadata.name}',
        )).strip()
        return output.split() if output else []

    def seed(self):
        pod = select_pod(self.pod_names(), self.target)
        logger.info('Seeding demo data in pod "{}"...'.format(pod))
        try:
            sh.kubectl('exec', pod, *self.namespace_args, '--', *self.command,
                       _out=sys.stdout.buffer, _err=sys.stdout.buffer)
        except sh.ErrorReturnCode as e:
            raise SeedError('Seeding pod "{}" failed: {}'.format(pod, e)) from e
        logger.info('Demo data seeded')

    def wait_and_seed(self, deployment_names):
        self.wait_for_rollout(deployment_names)
        self.seed()


class SeedCommand(base_command.InitialisedRepositoryCommand):
    """
    Runs dev_seed_command from config/kubeyard.yml inside the deployed pod.

    \b
    Example:
    dev_seed_command: python -m tests.demo
    dev_seed_pod: api
    """

    def run(self):
        super().run()
        if not self.context.get('DEV_SEED_COMMAND'):
            raise base_command.CommandException(
                'dev_seed_command is not set in config/kubeyard.yml.')
        SeedRunner(self.context).seed()
