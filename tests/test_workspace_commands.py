import logging
import pathlib

from unittest import mock

import pytest
import sh

from click.testing import CliRunner

from kubeyard import base_command
from kubeyard import preconditions
from kubeyard import workspace as workspace_module
from kubeyard.commands import workspace as workspace_commands
from kubeyard.entrypoints.kubeyard import cli

PROJECT_DIR = pathlib.Path('/home/dev/work/project')


@pytest.fixture(autouse=True)
def _restore_kubeyard_logger_level():
    """
    BaseWorkspaceCommand.run() sets the level of the shared 'kubeyard' logger
    as a side effect (via InitialisedRepositoryCommand.set_log_level). Left
    unrestored, that leaks across tests and could mask DEBUG-level
    assertions elsewhere in the suite.
    """
    kubeyard_logger = logging.getLogger('kubeyard')
    original_level = kubeyard_logger.level
    yield
    kubeyard_logger.setLevel(original_level)


def context(workspace='', mode='development'):
    namespace = workspace_module.namespace_for(workspace) if workspace else ''
    return {
        'KUBEYARD_MODE': mode,
        'KUBEYARD_WORKSPACE': workspace,
        'KUBEYARD_NAMESPACE': namespace,
    }


class BypassInitMixin:
    """
    Bypasses InitialisedRepositoryCommand.__init__, which needs click-provided
    directory/log_level and a real project context. Mirrors the approach used
    for other command tests (see tests/test_shell.py).
    """

    def __init__(self, ctx, project_dir=PROJECT_DIR, **extra):
        self._context = ctx
        self._project_dir = project_dir
        self._log_level = 'INFO'
        for key, value in extra.items():
            setattr(self, key, value)

    @property
    def context(self):
        return self._context

    @property
    def project_dir(self):
        return self._project_dir


class FakeCreateWorkspaceCommand(BypassInitMixin, workspace_commands.CreateWorkspaceCommand):
    pass


class FakeDestroyWorkspaceCommand(BypassInitMixin, workspace_commands.DestroyWorkspaceCommand):
    pass


class FakeShowWorkspaceCommand(BypassInitMixin, workspace_commands.ShowWorkspaceCommand):
    pass


class FakeSyncWorkspaceCommand(BypassInitMixin, workspace_commands.SyncWorkspaceCommand):
    pass


class TestResolveTargetName:
    def test_explicit_name_wins(self):
        assert workspace_commands.resolve_target_name('EXAMPLE', active='other') == 'example'

    def test_falls_back_to_active_workspace(self):
        assert workspace_commands.resolve_target_name(None, active='example') == 'example'

    def test_raises_when_neither_is_available(self):
        with pytest.raises(workspace_commands.NoWorkspaceSelected):
            workspace_commands.resolve_target_name(None, active='')

    def test_error_message_explains_how_to_select_one(self):
        with pytest.raises(workspace_commands.NoWorkspaceSelected) as excinfo:
            workspace_commands.resolve_target_name(None, active='')

        assert 'workspace create' in str(excinfo.value)


class TestCreateNameFallback:
    def test_uses_explicit_name(self):
        assert workspace_commands.resolve_create_name('EXAMPLE', branch='ignored') == 'example'

    def test_falls_back_to_branch(self):
        assert workspace_commands.resolve_create_name(None, branch='EXAMPLE') == 'example'

    def test_raises_on_detached_head_without_name(self):
        with pytest.raises(workspace_commands.NoWorkspaceSelected) as excinfo:
            workspace_commands.resolve_create_name(None, branch='')

        assert 'detached' in str(excinfo.value).lower()


class TestCurrentBranch:
    def test_returns_stripped_branch_name(self):
        with mock.patch.object(workspace_commands.sh, 'git', return_value='main\n') as git:
            assert workspace_commands.current_branch(PROJECT_DIR) == 'main'

        git.assert_called_once_with('-C', str(PROJECT_DIR), 'symbolic-ref', '--short', 'HEAD')

    def test_detached_head_returns_empty_string(self):
        error = sh.ErrorReturnCode('git', b'', b'fatal: ref HEAD is not a symbolic ref')
        with mock.patch.object(workspace_commands.sh, 'git', side_effect=error):
            assert workspace_commands.current_branch(PROJECT_DIR) == ''


class TestDestroyNamespaceSafety:
    """
    The single most important safety property: destroy must be structurally
    incapable of targeting the shared `default` namespace.
    """

    @pytest.mark.parametrize('attempted_name', ['default', 'DEFAULT', 'kube-system'])
    def test_namespace_for_any_workspace_name_is_never_the_shared_default(self, attempted_name):
        namespace = workspace_module.namespace_for(workspace_module.validate_name(attempted_name))

        assert namespace != workspace_module.DEFAULT_NAMESPACE

    def test_run_refuses_and_touches_nothing_when_no_name_and_no_active_workspace(self):
        command = FakeDestroyWorkspaceCommand(context(), name=None)

        with mock.patch.object(workspace_commands.preconditions, 'check_all'):
            with mock.patch.object(workspace_commands.sh, 'kubectl') as kubectl:
                with mock.patch('kubeyard.commands.deploy.DomainConfigurator') as domain_cls:
                    with pytest.raises(workspace_commands.NoWorkspaceSelected):
                        command.run()

        kubectl.assert_not_called()
        domain_cls.assert_not_called()


class TestDestroyWorkspaceCommandRun:
    def _run(self, ctx, name=None):
        command = FakeDestroyWorkspaceCommand(ctx, name=name)
        with mock.patch.object(workspace_commands.preconditions, 'check_all') as check_all, \
                mock.patch.object(workspace_commands.sh, 'kubectl', return_value='') as kubectl, \
                mock.patch('kubeyard.commands.deploy.DomainConfigurator') as domain_cls, \
                mock.patch.object(workspace_module, 'remove_marker') as remove_marker:
            command.run()
        return check_all, kubectl, domain_cls, remove_marker

    def test_preconditions_checked_before_any_kubectl_call(self):
        command = FakeDestroyWorkspaceCommand(context('example'), name=None)
        with mock.patch.object(
                workspace_commands.preconditions, 'check_all',
                side_effect=preconditions.PreconditionFailed('nope')):
            with mock.patch.object(workspace_commands.sh, 'kubectl') as kubectl:
                with mock.patch('kubeyard.commands.deploy.DomainConfigurator') as domain_cls:
                    with pytest.raises(preconditions.PreconditionFailed):
                        command.run()

        kubectl.assert_not_called()
        domain_cls.assert_not_called()

    def test_deletes_the_namespace_derived_from_the_resolved_name(self):
        check_all, kubectl, domain_cls, remove_marker = self._run(context('example'), name=None)

        delete_call = kubectl.call_args_list[0]
        assert delete_call.args[:3] == ('delete', 'namespace', 'ws-example')

    def test_explicit_name_overrides_active_workspace(self):
        check_all, kubectl, domain_cls, remove_marker = self._run(context('active'), name='OTHER')

        delete_call = kubectl.call_args_list[0]
        assert delete_call.args[:3] == ('delete', 'namespace', 'ws-other')

    def test_explicit_name_default_still_maps_to_a_ws_prefixed_namespace(self):
        # Pin the structural safety invariant at the level that actually
        # matters: what run() hands to kubectl, not just what namespace_for
        # returns in isolation.
        check_all, kubectl, domain_cls, remove_marker = self._run(context('active'), name='default')

        delete_call = kubectl.call_args_list[0]
        assert delete_call.args[:3] == ('delete', 'namespace', 'ws-default')

    def test_removes_domain_entries_for_the_resolved_name(self):
        ctx = context('example')
        check_all, kubectl, domain_cls, remove_marker = self._run(ctx, name=None)

        domain_cls.assert_called_once_with(ctx)
        domain_cls.return_value.remove.assert_called_once_with('example')

    def test_marker_removed_when_destroying_the_active_workspace(self):
        check_all, kubectl, domain_cls, remove_marker = self._run(context('example'), name=None)

        remove_marker.assert_called_once_with(PROJECT_DIR)

    def test_marker_untouched_when_destroying_a_different_workspace(self):
        check_all, kubectl, domain_cls, remove_marker = self._run(context('active'), name='other')

        remove_marker.assert_not_called()

    def test_no_warning_when_delete_succeeds(self, caplog):
        with caplog.at_level('WARNING'):
            self._run(context('example'), name=None)

        assert not any('finaliz' in record.message for record in caplog.records)

    def _run_with_failing_delete(self, command):
        # delete --wait=true either succeeds or exits non-zero, so the failure path
        # is only reachable by making the delete itself raise.
        delete_error = sh.ErrorReturnCode('kubectl', b'', b'timed out waiting for the condition')

        def kubectl_side_effect(*args, **kwargs):
            if args[0] == 'delete':
                raise delete_error
            return ''

        with mock.patch.object(workspace_commands.preconditions, 'check_all'):
            with mock.patch.object(workspace_commands.sh, 'kubectl', side_effect=kubectl_side_effect):
                with mock.patch('kubeyard.commands.deploy.DomainConfigurator') as domain_cls:
                    with mock.patch.object(workspace_module, 'remove_marker') as remove_marker:
                        with pytest.raises(base_command.CommandException) as excinfo:
                            command.run()
        return excinfo.value, domain_cls, remove_marker

    def test_delete_failure_fails_the_command_instead_of_exiting_zero(self):
        # A wedged namespace is not a destroyed workspace: every Deployment,
        # Service and database in it is still running, so a script that only
        # looks at the exit status must not be told this succeeded.
        command = FakeDestroyWorkspaceCommand(context('example'), name=None)

        error, _, _ = self._run_with_failing_delete(command)

        assert isinstance(error, base_command.CommandException)  # not a raw sh traceback

    def test_delete_failure_names_the_stuck_namespace_and_says_what_was_only_local(self):
        command = FakeDestroyWorkspaceCommand(context('example'), name=None)

        error, _, _ = self._run_with_failing_delete(command)

        message = str(error)
        assert 'ws-example' in message
        assert 'detached locally' in message.lower()

    def test_success_reports_destroyed_rather_than_merely_detached(self, caplog):
        with caplog.at_level('INFO'):
            self._run(context('example'), name=None)

        messages = [record.message for record in caplog.records]
        assert any('destroyed' in message for message in messages)
        assert not any('detached locally' in message.lower() for message in messages)

    def test_delete_failure_never_claims_the_workspace_was_destroyed(self, caplog):
        command = FakeDestroyWorkspaceCommand(context('example'), name=None)

        with caplog.at_level('INFO'):
            self._run_with_failing_delete(command)

        assert not any('destroyed' in record.message for record in caplog.records)

    def test_delete_failure_still_cleans_up_hosts_entries_and_marker(self):
        # The whole point of the fix: a wedged namespace must not leave
        # stale /etc/hosts entries or a marker attaching the worktree to a
        # dead workspace.
        command = FakeDestroyWorkspaceCommand(context('example'), name=None)

        _, domain_cls, remove_marker = self._run_with_failing_delete(command)

        domain_cls.return_value.remove.assert_called_once_with('example')
        remove_marker.assert_called_once_with(PROJECT_DIR)


class TestCreateWorkspaceCommandRun:
    def _run(self, ctx, name=None, branch='example', create_error=None):
        command = FakeCreateWorkspaceCommand(ctx, name=name)

        def kubectl_side_effect(*args, **kwargs):
            if args[:2] == ('create', 'namespace') and create_error is not None:
                raise create_error
            return ''

        with mock.patch.object(workspace_commands.preconditions, 'check_all') as check_all, \
                mock.patch.object(workspace_commands, 'current_branch', return_value=branch), \
                mock.patch.object(workspace_commands.sh, 'kubectl', side_effect=kubectl_side_effect) as kubectl, \
                mock.patch.object(workspace_module, 'write_marker') as write_marker, \
                mock.patch.object(workspace_commands.kubernetes, 'setup_cluster_context') as setup_cluster_context, \
                mock.patch.object(workspace_commands.kubernetes, 'install_global_secrets') as install_secrets, \
                mock.patch.object(workspace_commands.aliases, 'sync') as sync, \
                mock.patch.object(workspace_commands.sh, 'git') as git:
            sync.return_value = mock.Mock(to_create=[], to_delete=[])
            command.run()
        return dict(
            check_all=check_all, kubectl=kubectl, write_marker=write_marker,
            setup_cluster_context=setup_cluster_context, install_secrets=install_secrets,
            sync=sync, git=git,
        )

    def test_preconditions_checked_before_any_mutation(self):
        command = FakeCreateWorkspaceCommand(context(), name='example')
        with mock.patch.object(
                workspace_commands.preconditions, 'check_all',
                side_effect=preconditions.PreconditionFailed('nope')):
            with mock.patch.object(workspace_commands.sh, 'kubectl') as kubectl:
                with mock.patch.object(workspace_module, 'write_marker') as write_marker:
                    with pytest.raises(preconditions.PreconditionFailed):
                        command.run()

        kubectl.assert_not_called()
        write_marker.assert_not_called()

    def test_detached_head_without_explicit_name_is_refused_before_any_mutation(self):
        command = FakeCreateWorkspaceCommand(context(), name=None)
        with mock.patch.object(workspace_commands.preconditions, 'check_all'):
            with mock.patch.object(workspace_commands, 'current_branch', return_value=''):
                with mock.patch.object(workspace_commands.sh, 'kubectl') as kubectl:
                    with mock.patch.object(workspace_module, 'write_marker') as write_marker:
                        with pytest.raises(workspace_commands.NoWorkspaceSelected):
                            command.run()

        kubectl.assert_not_called()
        write_marker.assert_not_called()

    def test_name_falls_back_to_current_branch(self):
        result = self._run(context(), name=None, branch='EXAMPLE')

        create_call = [c for c in result['kubectl'].call_args_list if c.args[:2] == ('create', 'namespace')][0]
        assert create_call.args == ('create', 'namespace', 'ws-example')
        result['write_marker'].assert_called_once_with(PROJECT_DIR, 'example')

    def test_namespace_created_and_labelled(self):
        result = self._run(context(), name='example')

        kubectl_calls = result['kubectl'].call_args_list
        assert kubectl_calls[0].args == ('create', 'namespace', 'ws-example')
        assert kubectl_calls[1].args == (
            'label', 'namespace', 'ws-example', 'kubeyard.io/workspace=example', '--overwrite')

    def test_namespace_already_existing_is_tolerated(self):
        error = sh.ErrorReturnCode('kubectl', b'', b'namespaces "ws-example" already exists')
        result = self._run(context(), name='example', create_error=error)

        # labelling still happens even though creation reported "already exists"
        kubectl_calls = result['kubectl'].call_args_list
        assert kubectl_calls[1].args[0] == 'label'

    def test_other_kubectl_errors_on_create_propagate_and_skip_labelling(self):
        error = sh.ErrorReturnCode('kubectl', b'', b'Forbidden')
        command = FakeCreateWorkspaceCommand(context(), name='example')

        def kubectl_side_effect(*args, **kwargs):
            if args[:2] == ('create', 'namespace'):
                raise error
            return ''

        with mock.patch.object(workspace_commands.preconditions, 'check_all'):
            with mock.patch.object(workspace_commands.sh, 'kubectl', side_effect=kubectl_side_effect) as kubectl:
                with mock.patch.object(workspace_module, 'write_marker') as write_marker:
                    with pytest.raises(sh.ErrorReturnCode):
                        command.run()

        assert kubectl.call_count == 1  # label was never attempted
        write_marker.assert_not_called()

    def test_bootstrap_passes_a_context_copy_with_the_namespace_set(self):
        original_context = context()
        result = self._run(original_context, name='example')

        passed_context = result['setup_cluster_context'].call_args.args[0]
        assert passed_context['KUBEYARD_NAMESPACE'] == 'ws-example'
        # the command's own context object must not be mutated
        assert original_context['KUBEYARD_NAMESPACE'] == ''

    def test_bootstrap_installs_global_secrets(self):
        result = self._run(context(), name='example')

        result['install_secrets'].assert_called_once()

    def test_missing_global_secrets_key_error_is_suppressed(self):
        command = FakeCreateWorkspaceCommand(context(), name='example')
        with mock.patch.object(workspace_commands.preconditions, 'check_all'):
            with mock.patch.object(workspace_commands.sh, 'kubectl', return_value=''):
                with mock.patch.object(workspace_module, 'write_marker'):
                    with mock.patch.object(workspace_commands.kubernetes, 'setup_cluster_context'):
                        with mock.patch.object(
                                workspace_commands.kubernetes, 'install_global_secrets',
                                side_effect=KeyError('KUBEYARD_GLOBAL_SECRETS')):
                            with mock.patch.object(workspace_commands.aliases, 'sync') as sync:
                                sync.return_value = mock.Mock(to_create=[], to_delete=[])
                                with mock.patch.object(workspace_commands.sh, 'git'):
                                    command.run()  # must not raise

    def test_aliases_synced_for_the_new_namespace(self):
        result = self._run(context(), name='example')

        result['sync'].assert_called_once_with('ws-example')

    def test_warns_when_marker_file_is_not_gitignored(self, caplog):
        command = FakeCreateWorkspaceCommand(context(), name='example')
        with mock.patch.object(workspace_commands.preconditions, 'check_all'):
            with mock.patch.object(workspace_commands.sh, 'kubectl', return_value=''):
                with mock.patch.object(workspace_module, 'write_marker'):
                    with mock.patch.object(workspace_commands.kubernetes, 'setup_cluster_context'):
                        with mock.patch.object(workspace_commands.kubernetes, 'install_global_secrets'):
                            with mock.patch.object(workspace_commands.aliases, 'sync') as sync:
                                sync.return_value = mock.Mock(to_create=[], to_delete=[])
                                git_error = sh.ErrorReturnCode('git', b'', b'')
                                with mock.patch.object(
                                        workspace_commands.sh, 'git', side_effect=git_error):
                                    with caplog.at_level('WARNING'):
                                        command.run()

        assert any('gitignored' in record.message for record in caplog.records)

    def test_no_warning_when_marker_file_is_gitignored(self, caplog):
        self._run(context(), name='example')

        assert not any('gitignored' in record.message for record in caplog.records)


class TestShowWorkspaceCommand:
    @pytest.fixture
    def kubectl_context_ok(self):
        """Bypasses the kubectl-context check pinned by the two tests below it."""
        with mock.patch.object(
                workspace_commands.preconditions, 'current_kubectl_context', return_value='minikube'):
            yield

    def test_prints_shared_environment_message_when_inactive(self, capsys):
        command = FakeShowWorkspaceCommand(context())
        with mock.patch.object(workspace_commands.aliases, 'list_real_services') as list_real:
            command.run()

        list_real.assert_not_called()
        assert 'shared environment' in capsys.readouterr().out

    def test_refuses_before_querying_the_cluster_on_an_unexpected_context(self):
        # Same check ListWorkspacesCommand makes: a workspace summary listing
        # some other cluster's Services, under a local workspace name, is
        # worse than a refusal.
        command = FakeShowWorkspaceCommand(context('example'))

        with mock.patch.object(
                workspace_commands.preconditions, 'current_kubectl_context', return_value='gke-production'):
            with mock.patch.object(workspace_commands.aliases, 'list_real_services') as list_real:
                with pytest.raises(preconditions.PreconditionFailed):
                    command.run()

        list_real.assert_not_called()

    def test_no_cluster_check_is_needed_to_say_no_workspace_is_active(self):
        command = FakeShowWorkspaceCommand(context())

        with mock.patch.object(workspace_commands.preconditions, 'current_kubectl_context') as current_ctx:
            command.run()

        current_ctx.assert_not_called()

    def test_prints_workspace_summary_when_active(self, capsys, kubectl_context_ok):
        command = FakeShowWorkspaceCommand(context('example'))
        with mock.patch.object(workspace_commands.aliases, 'list_real_services', return_value={'web'}) as list_real:
            with mock.patch.object(
                    workspace_commands.aliases, 'list_aliases', return_value={'accounts'}) as list_aliases:
                with mock.patch.object(
                        workspace_commands.aliases, 'list_shared_services',
                        return_value={'accounts', 'billing'}) as list_shared:
                    command.run()

        list_real.assert_called_once_with('ws-example')
        list_aliases.assert_called_once_with('ws-example')
        list_shared.assert_called_once_with()
        output = capsys.readouterr().out
        assert 'Workspace: example' in output
        assert 'Namespace: ws-example' in output
        assert 'Deployed here (1): web' in output
        assert 'Aliased to default (1): accounts' in output
        assert 'Missing aliases (1): billing' in output

    def test_no_missing_aliases_line_when_nothing_is_stale(self, capsys, kubectl_context_ok):
        command = FakeShowWorkspaceCommand(context('example'))
        with mock.patch.object(workspace_commands.aliases, 'list_real_services', return_value=set()):
            with mock.patch.object(workspace_commands.aliases, 'list_aliases', return_value={'accounts'}):
                with mock.patch.object(workspace_commands.aliases, 'list_shared_services', return_value={'accounts'}):
                    command.run()

        assert 'Missing aliases' not in capsys.readouterr().out


class TestListWorkspacesCommand:
    def test_checks_kubectl_context_before_listing_anything(self):
        with mock.patch.object(
                workspace_commands.preconditions, 'current_kubectl_context', return_value='minikube') as current_ctx:
            with mock.patch.object(workspace_commands.preconditions, 'check_kubectl_context') as check_ctx:
                with mock.patch.object(workspace_commands.sh, 'kubectl', return_value='') as kubectl:
                    workspace_commands.ListWorkspacesCommand().run()

        current_ctx.assert_called_once_with()
        check_ctx.assert_called_once_with('minikube')
        kubectl.assert_called_once()  # only the "get namespaces" call

    def test_refuses_before_touching_namespaces_on_unexpected_context(self):
        with mock.patch.object(
                workspace_commands.preconditions, 'current_kubectl_context', return_value='gke-production'):
            with mock.patch.object(
                    workspace_commands.preconditions, 'check_kubectl_context',
                    side_effect=preconditions.PreconditionFailed('nope')):
                with mock.patch.object(workspace_commands.sh, 'kubectl') as kubectl:
                    with pytest.raises(preconditions.PreconditionFailed):
                        workspace_commands.ListWorkspacesCommand().run()

        kubectl.assert_not_called()

    def test_builds_the_selector_and_a_custom_column_whose_jsonpath_key_round_trips(self):
        with mock.patch.object(workspace_commands.preconditions, 'check_kubectl_context'):
            with mock.patch.object(
                    workspace_commands.preconditions, 'current_kubectl_context', return_value='minikube'):
                with mock.patch.object(workspace_commands.sh, 'kubectl', return_value='') as kubectl:
                    workspace_commands.ListWorkspacesCommand().run()

        args = kubectl.call_args.args
        assert args[0:4] == ('get', 'namespaces', '--selector', workspace_commands.WORKSPACE_LABEL)
        assert args[-1] == '--no-headers'
        output_value = args[args.index('--output') + 1]
        prefix = 'custom-columns=NAME:.metadata.labels.'
        assert output_value.startswith(prefix)
        jsonpath_key = output_value[len(prefix):]
        # Only "." is a jsonpath separator, so "/" must stay literal. Round-tripping
        # the escaping is what catches escaping the wrong character.
        assert jsonpath_key.replace('\\.', '.') == workspace_commands.WORKSPACE_LABEL
        assert '\\.' in jsonpath_key  # a dot really was escaped
        assert '/' in jsonpath_key  # the slash really was left alone

    def test_prints_no_workspaces_when_empty(self, capsys):
        with mock.patch.object(workspace_commands.preconditions, 'check_kubectl_context'):
            with mock.patch.object(workspace_commands.preconditions, 'current_kubectl_context'):
                with mock.patch.object(workspace_commands.sh, 'kubectl', return_value='  '):
                    workspace_commands.ListWorkspacesCommand().run()

        assert capsys.readouterr().out.strip() == 'No workspaces.'

    def test_prints_output_when_present(self, capsys):
        with mock.patch.object(workspace_commands.preconditions, 'check_kubectl_context'):
            with mock.patch.object(workspace_commands.preconditions, 'current_kubectl_context'):
                with mock.patch.object(workspace_commands.sh, 'kubectl', return_value='example\nother\n'):
                    workspace_commands.ListWorkspacesCommand().run()

        assert capsys.readouterr().out.strip() == 'example\nother'


class TestSyncWorkspaceCommand:
    def test_refuses_when_no_workspace_is_active(self):
        command = FakeSyncWorkspaceCommand(context())
        with mock.patch.object(workspace_commands.preconditions, 'check_all'):
            with mock.patch.object(workspace_commands.aliases, 'sync') as sync:
                with pytest.raises(workspace_commands.NoWorkspaceSelected):
                    command.run()

        sync.assert_not_called()

    def test_preconditions_checked_before_syncing(self):
        command = FakeSyncWorkspaceCommand(context('example'))
        with mock.patch.object(
                workspace_commands.preconditions, 'check_all',
                side_effect=preconditions.PreconditionFailed('nope')):
            with mock.patch.object(workspace_commands.aliases, 'sync') as sync:
                with pytest.raises(preconditions.PreconditionFailed):
                    command.run()

        sync.assert_not_called()

    def test_syncs_the_active_workspace_namespace_and_prints_result(self, capsys):
        command = FakeSyncWorkspaceCommand(context('example'))
        with mock.patch.object(workspace_commands.preconditions, 'check_all'):
            with mock.patch.object(workspace_commands.aliases, 'sync') as sync:
                sync.return_value = mock.Mock(to_create=['billing'], to_delete=['stale'])
                command.run()

        sync.assert_called_once_with('ws-example')
        output = capsys.readouterr().out
        assert 'Created 1 aliases, removed 1.' in output
        assert '+ billing' in output
        assert '- stale' in output

    def test_a_failed_service_listing_reports_nothing_and_fails(self, capsys):
        # "Removed N" after a failed listing would read as the reconciliation
        # the user asked for, when in fact it wiped the whole overlay.
        command = FakeSyncWorkspaceCommand(context('example'))
        with mock.patch.object(workspace_commands.preconditions, 'check_all'):
            with mock.patch.object(
                    workspace_commands.aliases, 'sync',
                    side_effect=workspace_commands.aliases.ServiceListingFailed('kubectl is unhappy')):
                with pytest.raises(workspace_commands.aliases.ServiceListingFailed):
                    command.run()

        assert capsys.readouterr().out == ''


class TestCliWiring:
    def test_workspace_group_lists_all_subcommands(self):
        result = CliRunner().invoke(cli, ['workspace', '--help'])

        assert result.exit_code == 0
        for subcommand in ('create', 'destroy', 'show', 'list', 'sync'):
            assert subcommand in result.output
