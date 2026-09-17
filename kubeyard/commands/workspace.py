import contextlib
import logging
import pathlib
import sys

import click
import sh

from cached_property import cached_property

from kubeyard import aliases
from kubeyard import base_command
from kubeyard import kubernetes
from kubeyard import preconditions
from kubeyard import workspace as workspace_module
from kubeyard import worktree

logger = logging.getLogger(__name__)

WORKSPACE_LABEL = 'kubeyard.io/workspace'


class NoWorkspaceSelected(Exception):
    pass


def label_column(label) -> str:
    """jsonpath reads "." as a path separator, so a dot inside a label key must be escaped."""
    return 'custom-columns=NAME:.metadata.labels.{}'.format(label.replace('.', '\\.'))


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
    Creates a workspace namespace, attaches a working copy to it and configures its domains.

    Run in the main checkout it also creates the git worktree to work in, so the name is
    required there. Run inside a worktree it attaches that one, and the name defaults to
    the current branch.
    """

    def __init__(self, *, name, worktree_root=None, print_path=False, **kwargs):
        super().__init__(**kwargs)
        self.name = name
        self.worktree_root = worktree_root
        self.print_path = print_path

    def run(self):
        super().run()
        self.check_preconditions()
        in_main_checkout = worktree.is_main_checkout(self.project_dir)
        name = self.resolve_name(in_main_checkout)
        namespace = workspace_module.namespace_for(name)
        attached_to = self.prepare_worktree(name) if in_main_checkout else self.project_dir
        self.ensure_namespace(name, namespace)
        workspace_module.write_marker(attached_to, name)
        logger.info('Workspace "{}" attached to {}'.format(name, attached_to))
        self.bootstrap(namespace)
        result = aliases.sync(namespace)
        logger.info('Aliases: {} created, {} removed'.format(len(result.to_create), len(result.to_delete)))
        self.warn_if_not_gitignored()
        self.report(name, attached_to, in_main_checkout)

    def resolve_name(self, in_main_checkout):
        if in_main_checkout and not self.name:
            raise NoWorkspaceSelected(
                'A workspace name is required here, because this is the main checkout and its branch '
                'names the shared environment rather than a workspace: kubeyard workspace create <name>')
        return resolve_create_name(self.name, worktree.name_from_branch(current_branch(self.project_dir)))

    def prepare_worktree(self, name):
        root = worktree.resolve_root(self.worktree_root, self.context)
        path = worktree.path_for(self.project_dir, root, name)
        branch = worktree.branch_for(name)
        if worktree.ensure(self.project_dir, path, branch):
            logger.info('Created worktree {} on branch "{}"'.format(path, branch))
        else:
            logger.info('Reusing existing worktree {}'.format(path))
        self.warn_if_root_not_gitignored(root)
        return path

    def warn_if_root_not_gitignored(self, root):
        try:
            sh.git('-C', str(self.project_dir), 'check-ignore', '-q', root)
        except sh.ErrorReturnCode:
            logger.warning(
                '{} is not gitignored, so git will offer to commit the worktree into the branch '
                'it was made from. Add it to the repository .gitignore.'.format(root))

    def report(self, name, attached_to, in_main_checkout):
        if self.print_path:
            print(attached_to)
        elif in_main_checkout:
            self.print_next_steps(name, self.displayable(attached_to))

    def print_next_steps(self, name, path):
        """
        Set off from the log lines above it, because this is the one part of the
        output the developer has to act on.
        """
        click.echo()
        click.secho('Workspace {!r} is ready:'.format(name), bold=True)
        click.echo()
        click.echo('    cd {}'.format(path))
        click.echo('    kubeyard build && kubeyard deploy')
        click.echo()
        click.echo('When you are finished with it:')
        click.echo()
        click.echo('    kubeyard workspace destroy')
        click.echo('    git worktree remove {}'.format(path))

    def displayable(self, path):
        try:
            return path.relative_to(pathlib.Path(self.project_dir).resolve())
        except ValueError:
            return path

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
                '{} is not gitignored. Add it to the repository .gitignore, so everyone '
                'working on it benefits.'.format(workspace_module.MARKER_FILENAME))


class DestroyWorkspaceCommand(BaseWorkspaceCommand):
    """
    Deletes a workspace namespace, its /etc/hosts entries and the local marker file.

    The git worktree is left alone: it may hold work that exists nowhere else. Remove it
    yourself with "git worktree remove" once you are sure.
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
        # Deletion can hang on finalizers, but a marker pointing at a dying
        # namespace helps nobody, and destroy is idempotent.
        try:
            self.delete_namespace(namespace)
        finally:
            self.detach_locally(name)
        logger.info('Workspace "{}" destroyed. The worktree is untouched; remove it with '
                    '"git worktree remove" when you no longer need it.'.format(name))

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
        preconditions.check_cluster_is_the_expected_one()
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
        preconditions.check_cluster_is_the_expected_one()
        output = str(sh.kubectl(
            'get', 'namespaces', '--selector', WORKSPACE_LABEL,
            '--output', label_column(WORKSPACE_LABEL),
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
