import logging
import sys

import sh

from cached_property import cached_property

from kubeyard import aliases
from kubeyard import base_command
from kubeyard import kubectl as kubectl_helper
from kubeyard import preconditions
from kubeyard.commands import deploy

logger = logging.getLogger(__name__)


class UndeployRefused(Exception):
    pass


def check_allowed(context):
    if context.get('KUBEYARD_MODE') != 'development':
        raise UndeployRefused(
            'Refusing to undeploy: KUBEYARD_MODE is not "development". '
            'Use kubectl directly if you really mean to remove production objects.')


def confirmation_required(context) -> bool:
    return not context.get('KUBEYARD_NAMESPACE')


def is_uninstalled_resource_type(stderr: bytes) -> bool:
    """A kind the API server does not know can have no objects, so there is nothing to delete."""
    return b"server doesn't have a resource type" in stderr


class UndeployCommand(base_command.InitialisedRepositoryCommand):
    """
    Removes this project's Kubernetes objects, the inverse of deploy.

    Inside a workspace it also restores the ExternalName aliases, so calls fall back to the
    shared instance. In the shared environment it asks for confirmation first, and it refuses
    outright in production mode. It never removes development requirements and never drops
    databases - use "kubeyard workspace destroy" for that.
    """

    def __init__(self, *, yes, **kwargs):
        super().__init__(**kwargs)
        self.yes = yes

    @property
    def namespace(self):
        return self.context.get('KUBEYARD_NAMESPACE', '')

    @property
    def namespace_args(self):
        return kubectl_helper.namespace_args(self.namespace)

    @cached_property
    def current_kubectl_context(self):
        return preconditions.current_kubectl_context()

    @property
    def definition_directories(self):
        # check_allowed already refuses to run outside development mode, so unlike
        # deploy there is no "is this a dev run" distinction left to make.
        return deploy.definition_directories(self.project_dir, include_dev_overrides=True)

    @property
    def targets(self):
        service_name = self.context.get('KUBE_SERVICE_NAME')
        if not service_name:
            raise base_command.CommandException(
                'KUBE_SERVICE_NAME is not set; cannot determine which Secret to remove.')
        objects = deploy.owned_objects(self.definition_directories)
        objects.append(('Secret', service_name))
        return objects

    def run(self):
        super().run()
        check_allowed(self.context)
        # KUBEYARD_MODE is a machine-level setting that says nothing about which
        # cluster kubectl points at, so it cannot stand in for this check.
        preconditions.check_kubectl_context(self.current_kubectl_context)
        targets = self.targets
        if not targets:
            logger.info('Nothing to undeploy.')
            return
        self.confirm(targets)
        failures, skipped = self.delete_targets(targets)
        if self.namespace:
            self.restore_aliases()
        self.report_result(targets, failures, skipped)

    def confirm(self, targets):
        if not confirmation_required(self.context):
            return
        print('About to delete from kubectl context {!r}, the namespace of your current '
              'context:'.format(self.current_kubectl_context))
        for kind, name in targets:
            print('  {}/{}'.format(kind, name))
        if self.yes:
            return
        if not sys.stdin.isatty():
            raise UndeployRefused(
                'Refusing to undeploy from the shared environment without confirmation. '
                'Re-run with --yes if you really mean it.')
        answer = input('Delete these objects from kubectl context {!r}? [y/N] '.format(self.current_kubectl_context))
        if answer.strip().lower() not in ('y', 'yes'):
            raise UndeployRefused('Aborted.')

    def delete_targets(self, targets):
        """
        Failures are collected rather than raised, so that run() still restores the
        aliases: a half-finished undeploy must not leave a name resolving to nothing.
        """
        failures = []
        skipped = []
        for kind, name in targets:
            try:
                self.delete_one(kind, name)
            except sh.ErrorReturnCode as e:
                if is_uninstalled_resource_type(e.stderr):
                    logger.warning(
                        'Resource type {} is not installed in this cluster, so {}/{} cannot exist; '
                        'skipping it.'.format(kind, kind, name))
                    skipped.append((kind, name))
                else:
                    logger.warning('Failed to delete {}/{}; left in place. ({})'.format(
                        kind, name, e.stderr.decode(errors='replace').strip()))
                    failures.append((kind, name))
        return failures, skipped

    def delete_one(self, kind, name):
        sh.kubectl('delete', kind.lower(), name, *self.namespace_args, '--ignore-not-found',
                   _out=sys.stdout.buffer)

    def report_result(self, targets, failures, skipped):
        """
        A partial failure is deliberately not fatal; deleting nothing is, because
        exiting 0 would tell a script the undeploy succeeded.
        """
        succeeded = len(targets) - len(failures) - len(skipped)
        if skipped:
            logger.warning(
                'Skipped {} of {} objects whose resource type is not installed in this cluster: {}.'.format(
                    len(skipped), len(targets), self._describe(skipped)))
        if failures and not succeeded:
            raise base_command.CommandException(
                'Undeployed nothing: all {} objects that could be deleted failed ({}). Check "kubectl describe" '
                'for each, then re-run "kubeyard undeploy" once resolved.'.format(
                    len(failures), self._describe(failures)))
        if failures:
            logger.warning(
                'Undeployed {} of {} objects; {} failed and were left in place: {}. Check "kubectl describe" '
                'for each, then re-run "kubeyard undeploy" once resolved.'.format(
                    succeeded, len(targets), len(failures), self._describe(failures)))
        else:
            logger.info('Undeployed {} objects.'.format(succeeded))

    @staticmethod
    def _describe(objects):
        return ', '.join('{}/{}'.format(kind, name) for kind, name in objects)

    def restore_aliases(self):
        try:
            shared_services = aliases.list_shared_services()
        except aliases.ServiceListingFailed as e:
            # The deletes already happened, so the names just removed now resolve
            # to nothing. That must not pass unmentioned.
            logger.warning(
                'Could not list the shared Services, so no aliases were restored: names this project owns '
                'now resolve to nothing inside {}. Run "kubeyard workspace sync" once kubectl works '
                'again. ({})'.format(self.namespace, e))
            return
        names = [
            name for name in deploy.owned_service_names(self.definition_directories)
            if name in shared_services
        ]
        if names:
            aliases.apply(self.namespace, names)
            logger.info('Restored aliases: {}'.format(', '.join(names)))
