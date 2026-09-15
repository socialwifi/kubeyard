import contextlib
import logging
import sys

import sh

from cached_property import cached_property

from kubeyard import aliases
from kubeyard import base_command
from kubeyard import kubernetes
from kubeyard import preconditions
from kubeyard import workspace as workspace_module

logger = logging.getLogger(__name__)

WORKSPACE_LABEL = 'kubeyard.io/workspace'


class NoWorkspaceSelected(Exception):
    pass


def resolve_target_name(explicit_name, active):
    if explicit_name:
        return workspace_module.validate_name(explicit_name)
    if active:
        return active
    raise NoWorkspaceSelected(
        'No workspace selected. Run this from a directory attached to a workspace '
        '(see "kubeyard workspace create"), or pass the workspace name explicitly.')


def resolve_create_name(explicit_name, branch):
    if explicit_name:
        return workspace_module.validate_name(explicit_name)
    if branch:
        return workspace_module.validate_name(branch)
    raise NoWorkspaceSelected(
        'No workspace name given and HEAD is detached, so there is no branch name to fall back on. '
        'Pass the name explicitly: kubeyard workspace create <name>')


def current_branch(project_dir) -> str:
    try:
        return str(sh.git('-C', str(project_dir), 'symbolic-ref', '--short', 'HEAD')).strip()
    except sh.ErrorReturnCode:
        return ''


class BaseWorkspaceCommand(base_command.InitialisedRepositoryCommand):
    def check_preconditions(self):
        preconditions.check_all(self.context, self.project_dir)

    @cached_property
    def active_workspace(self):
        return self.context.get('KUBEYARD_WORKSPACE', '')


class CreateWorkspaceCommand(BaseWorkspaceCommand):
    """
    Creates a workspace namespace, attaches this repository to it and configures its domains.

    The workspace name defaults to the current git branch. On a detached HEAD the name is required.
    """

    def __init__(self, *, name, **kwargs):
        super().__init__(**kwargs)
        self.name = name

    def run(self):
        super().run()
        self.check_preconditions()
        name = resolve_create_name(self.name, current_branch(self.project_dir))
        namespace = workspace_module.namespace_for(name)
        self.ensure_namespace(name, namespace)
        workspace_module.write_marker(self.project_dir, name)
        logger.info('Workspace "{}" attached to {}'.format(name, self.project_dir))
        self.bootstrap(namespace)
        result = aliases.sync(namespace)
        logger.info('Aliases: {} created, {} removed'.format(len(result.to_create), len(result.to_delete)))
        self.warn_if_not_gitignored()

    def ensure_namespace(self, name, namespace):
        try:
            sh.kubectl('create', 'namespace', namespace)
        except sh.ErrorReturnCode as e:
            if b'already exists' not in e.stderr:
                raise
            logger.info('Namespace "{}" already exists'.format(namespace))
        sh.kubectl(
            'label', 'namespace', namespace,
            '{}={}'.format(WORKSPACE_LABEL, name), '--overwrite',
        )

    def bootstrap(self, namespace):
        context = dict(self.context)
        context['KUBEYARD_NAMESPACE'] = namespace
        kubernetes.setup_cluster_context(context)
        with contextlib.suppress(KeyError):
            kubernetes.install_global_secrets(context)

    def warn_if_not_gitignored(self):
        try:
            sh.git('-C', str(self.project_dir), 'check-ignore', '-q', workspace_module.MARKER_FILENAME)
        except sh.ErrorReturnCode:
            logger.warning(
                '{} is not gitignored. Add it to ~/.config/git/ignore so it is never '
                'committed.'.format(workspace_module.MARKER_FILENAME))


class DestroyWorkspaceCommand(BaseWorkspaceCommand):
    """
    Deletes a workspace namespace, its /etc/hosts entries and the local marker file.
    """

    def __init__(self, *, name, **kwargs):
        super().__init__(**kwargs)
        self.name = name

    def run(self):
        super().run()
        self.check_preconditions()
        name = resolve_target_name(self.name, self.active_workspace)
        namespace = workspace_module.namespace_for(name)
        logger.info('Deleting namespace {}...'.format(namespace))
        # The namespace delete may not have finished (it can be blocked on
        # finalizers), but the user asked for the workspace to be gone: stale
        # /etc/hosts entries and a marker pointing at a dying namespace are
        # never useful, so local cleanup always runs - hence the finally.
        # destroy is idempotent, so re-running once the namespace actually
        # disappears is safe.
        try:
            self.delete_namespace(namespace)
        finally:
            self.detach_locally(name)
        logger.info('Workspace "{}" destroyed'.format(name))

    def detach_locally(self, name):
        from kubeyard.commands.deploy import DomainConfigurator
        DomainConfigurator(self.context).remove(name)
        if name == self.active_workspace:
            workspace_module.remove_marker(self.project_dir)

    def delete_namespace(self, namespace):
        """
        Delete the namespace, failing the command if it did not go away.

        A wedged namespace is not a destroyed workspace: reporting success
        would tell a script the cluster is clean when its Deployments, Services
        and database are all still running.
        """
        try:
            sh.kubectl(
                'delete', 'namespace', namespace, '--ignore-not-found', '--wait=true',
                _out=sys.stdout, _err=sys.stderr,
            )
        except sh.ErrorReturnCode as e:
            raise base_command.CommandException(
                'Workspace detached locally, but namespace {namespace} did not finish deleting - most likely '
                'blocked on finalizers; check with "kubectl get namespace {namespace} -o yaml". The local '
                '/etc/hosts entries and workspace marker are removed anyway; re-run '
                '"kubeyard workspace destroy" once the namespace is actually gone.'.format(
                    namespace=namespace)) from e


class ShowWorkspaceCommand(BaseWorkspaceCommand):
    """Shows the active workspace and which services are real rather than aliased."""

    def run(self):
        super().run()
        name = self.active_workspace
        if not name:
            print('No workspace active in {}. Using the shared environment.'.format(self.project_dir))
            return
        # Read-only, but from here on it queries the cluster, so it gets the
        # same check ListWorkspacesCommand makes: listing the Services of
        # whatever cluster kubectl happens to point at, under the heading of a
        # local workspace name, is worse than refusing.
        preconditions.check_kubectl_context(preconditions.current_kubectl_context())
        namespace = workspace_module.namespace_for(name)
        real = sorted(aliases.list_real_services(namespace))
        aliased = sorted(aliases.list_aliases(namespace))
        shared = aliases.list_shared_services()
        stale = sorted(shared - set(real) - set(aliased))
        print('Workspace: {}'.format(name))
        print('Namespace: {}'.format(namespace))
        print('Deployed here ({}): {}'.format(len(real), ', '.join(real) or '-'))
        print('Aliased to default ({}): {}'.format(len(aliased), ', '.join(aliased) or '-'))
        if stale:
            print('Missing aliases ({}): {} - run "kubeyard workspace sync"'.format(len(stale), ', '.join(stale)))


class ListWorkspacesCommand(base_command.BaseCommand):
    """Lists all workspace namespaces in the cluster."""

    def run(self):
        # Read-only and not tied to a project directory, so check_all's other
        # preconditions don't apply; but a plain kubectl-context check keeps
        # this from being run against production without any safety property
        # actually depending on it.
        preconditions.check_kubectl_context(preconditions.current_kubectl_context())
        # jsonpath treats an unescaped "." as a path separator, so a literal
        # dot in the label key must be escaped; "/" is not a separator and
        # must stay literal, or kubectl silently resolves to a nonexistent
        # field and prints nothing for every workspace.
        output = str(sh.kubectl(
            'get', 'namespaces', '--selector', WORKSPACE_LABEL,
            '--output', 'custom-columns=NAME:.metadata.labels.{}'.format(WORKSPACE_LABEL.replace('.', '\\.')),
            '--no-headers',
        )).strip()
        print(output or 'No workspaces.')


class SyncWorkspaceCommand(BaseWorkspaceCommand):
    """Reconciles the alias overlay against the current contents of the default namespace."""

    def run(self):
        super().run()
        self.check_preconditions()
        name = resolve_target_name(None, self.active_workspace)
        result = aliases.sync(workspace_module.namespace_for(name))
        print('Created {} aliases, removed {}.'.format(len(result.to_create), len(result.to_delete)))
        for created in result.to_create:
            print('  + {}'.format(created))
        for removed in result.to_delete:
            print('  - {}'.format(removed))
