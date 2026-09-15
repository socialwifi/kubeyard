import logging
import pathlib

from unittest import mock

import pytest
import sh

from click.testing import CliRunner

from kubeyard import kubectl as kubectl_helper
from kubeyard.commands import undeploy
from kubeyard.entrypoints.kubeyard import cli

PROJECT_DIR = pathlib.Path('/home/dev/work/project')


@pytest.fixture(autouse=True)
def _restore_kubeyard_logger_level():
    """
    InitialisedRepositoryCommand.set_log_level mutates the shared 'kubeyard'
    logger as a side effect. Left unrestored, that leaks across tests.
    """
    kubeyard_logger = logging.getLogger('kubeyard')
    original_level = kubeyard_logger.level
    yield
    kubeyard_logger.setLevel(original_level)


@pytest.fixture
def kubectl_context_ok():
    """
    Bypasses the kubectl-context precondition (see TestRunKubectlContextGuard,
    which pins that precondition itself) so tests unrelated to it can reach
    the behaviour they actually target without shelling out to a real
    `kubectl config current-context`.
    """
    with mock.patch.object(undeploy.preconditions, 'current_kubectl_context', return_value='minikube'):
        yield


def context(mode='development', namespace='', service_name='web'):
    return {'KUBEYARD_MODE': mode, 'KUBEYARD_NAMESPACE': namespace, 'KUBE_SERVICE_NAME': service_name}


class BypassInitMixin:
    """
    Bypasses InitialisedRepositoryCommand.__init__, which needs click-provided
    directory/log_level and a real project context. Mirrors the approach used
    for other command tests (see tests/test_workspace_commands.py).
    """

    def __init__(self, ctx, *, project_dir=PROJECT_DIR, yes=False):
        self._context = ctx
        self._project_dir = project_dir
        self._log_level = 'INFO'
        self.yes = yes

    @property
    def context(self):
        return self._context

    @property
    def project_dir(self):
        return self._project_dir


class FakeUndeployCommand(BypassInitMixin, undeploy.UndeployCommand):
    pass


class TestProductionRefusal:
    def test_refuses_in_production(self):
        with pytest.raises(undeploy.UndeployRefused) as excinfo:
            undeploy.check_allowed(context(mode='production'))

        assert 'production' in str(excinfo.value).lower()

    def test_refuses_in_production_even_with_a_workspace(self):
        with pytest.raises(undeploy.UndeployRefused):
            undeploy.check_allowed(context(mode='production', namespace='ws-example'))

    def test_allows_development_with_workspace(self):
        undeploy.check_allowed(context(namespace='ws-example'))

    def test_allows_development_without_workspace(self):
        undeploy.check_allowed(context())

    def test_refuses_any_non_development_mode_not_just_the_literal_string_production(self):
        # The guard is a whitelist ("== development"), not a blacklist for
        # the word "production" - an unset or unknown mode must also refuse.
        with pytest.raises(undeploy.UndeployRefused):
            undeploy.check_allowed({'KUBEYARD_MODE': None, 'KUBEYARD_NAMESPACE': ''})

    def test_refuses_when_mode_key_is_entirely_absent(self):
        with pytest.raises(undeploy.UndeployRefused):
            undeploy.check_allowed({'KUBEYARD_NAMESPACE': ''})

    def test_message_points_at_kubectl_as_the_deliberate_escape_hatch(self):
        with pytest.raises(undeploy.UndeployRefused) as excinfo:
            undeploy.check_allowed(context(mode='production'))

        assert 'kubectl' in str(excinfo.value).lower()


class TestConfirmationRequired:
    def test_not_required_inside_a_workspace(self):
        assert undeploy.confirmation_required(context(namespace='ws-example')) is False

    def test_required_in_the_shared_environment(self):
        assert undeploy.confirmation_required(context()) is True


class TestNamespaceAndNamespaceArgs:
    def test_namespace_defaults_to_empty_string(self):
        assert FakeUndeployCommand(context()).namespace == ''

    def test_namespace_reads_from_context(self):
        assert FakeUndeployCommand(context(namespace='ws-example')).namespace == 'ws-example'

    def test_namespace_args_empty_when_inactive(self):
        assert FakeUndeployCommand(context()).namespace_args == ()

    def test_namespace_args_delegates_to_kubectl_helper_when_active(self):
        command = FakeUndeployCommand(context(namespace='ws-example'))

        assert command.namespace_args == kubectl_helper.namespace_args('ws-example')
        assert command.namespace_args == ('--namespace', 'ws-example')


class TestDefinitionDirectories:
    def test_both_directories_included_when_present(self, tmp_path):
        kubernetes_dir = tmp_path / 'config' / 'kubernetes' / 'deploy'
        overrides_dir = tmp_path / 'config' / 'kubernetes' / 'development_overrides'
        kubernetes_dir.mkdir(parents=True)
        overrides_dir.mkdir(parents=True)
        command = FakeUndeployCommand(context(), project_dir=tmp_path)

        assert command.definition_directories == [kubernetes_dir, overrides_dir]

    def test_only_existing_directories_are_included(self, tmp_path):
        kubernetes_dir = tmp_path / 'config' / 'kubernetes' / 'deploy'
        kubernetes_dir.mkdir(parents=True)
        command = FakeUndeployCommand(context(), project_dir=tmp_path)

        assert command.definition_directories == [kubernetes_dir]

    def test_empty_when_neither_directory_exists(self, tmp_path):
        command = FakeUndeployCommand(context(), project_dir=tmp_path)

        assert command.definition_directories == []


class TestTargets:
    def test_owned_objects_plus_the_secret(self, tmp_path):
        deploy_dir = tmp_path / 'config' / 'kubernetes' / 'deploy'
        deploy_dir.mkdir(parents=True)
        (deploy_dir / '01_deployment.yml').write_text('kind: Deployment\nmetadata:\n  name: web\n')
        (deploy_dir / '02_service.yml').write_text('kind: Service\nmetadata:\n  name: api\n')
        command = FakeUndeployCommand(context(service_name='web'), project_dir=tmp_path)

        assert command.targets == [('Deployment', 'web'), ('Service', 'api'), ('Secret', 'web')]

    def test_a_deployment_kept_only_in_the_base_file_is_still_a_target(self, tmp_path):
        """
        Real development_overrides files are fragments: they carry the keys
        they change and nothing else. Treating one as a replacement drops the
        kind and name, and the object silently stops being undeployed - which
        is exactly what left Deployments behind in the acceptance run.
        """
        deploy_dir = tmp_path / 'config' / 'kubernetes' / 'deploy'
        overrides_dir = tmp_path / 'config' / 'kubernetes' / 'development_overrides'
        deploy_dir.mkdir(parents=True)
        overrides_dir.mkdir(parents=True)
        (deploy_dir / '01_deployment.yml').write_text(
            'apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: web\nspec:\n  replicas: 3\n')
        (overrides_dir / '01_deployment.yml').write_text('spec:\n  replicas: 1\n')
        command = FakeUndeployCommand(context(service_name='web'), project_dir=tmp_path)

        assert command.targets == [('Deployment', 'web'), ('Secret', 'web')]

    def test_secret_is_always_present_even_with_no_owned_objects(self, tmp_path):
        command = FakeUndeployCommand(context(service_name='web'), project_dir=tmp_path)

        assert command.targets == [('Secret', 'web')]

    def test_secret_name_comes_from_kube_service_name(self, tmp_path):
        command = FakeUndeployCommand(context(service_name='api'), project_dir=tmp_path)

        assert command.targets == [('Secret', 'api')]

    def test_missing_kube_service_name_raises_a_kubeyard_error_not_a_bare_keyerror(self, tmp_path):
        command = FakeUndeployCommand({'KUBEYARD_MODE': 'development', 'KUBEYARD_NAMESPACE': ''}, project_dir=tmp_path)

        with pytest.raises(undeploy.base_command.CommandException) as excinfo:
            command.targets

        assert 'KUBE_SERVICE_NAME' in str(excinfo.value)

    def test_empty_kube_service_name_is_treated_the_same_as_missing(self, tmp_path):
        command = FakeUndeployCommand(context(service_name=''), project_dir=tmp_path)

        with pytest.raises(undeploy.base_command.CommandException):
            command.targets


class TestTargetsSourceIsOnlyTheRepoOwnDirectories:
    """
    Behavioural pin on "never touches dev_requirements infrastructure and
    never drops databases": targets is derived from exactly one call to
    deploy.owned_objects(self.definition_directories), plus the Secret, and
    nothing else - no dev_requirements/dependencies state can inject an
    additional target. (A source-text grep for "dev_requirements" was tried
    first and rejected: it is fooled by an indirection and false-fails on a
    docstring, so it is replaced with this behavioural equivalent instead.)
    """

    def test_targets_equals_owned_objects_plus_the_secret_and_nothing_else(self, tmp_path):
        command = FakeUndeployCommand(context(service_name='web'), project_dir=tmp_path)

        with mock.patch.object(undeploy.deploy, 'owned_objects', return_value=[('Deployment', 'web')]) as owned:
            result = command.targets

        owned.assert_called_once_with(command.definition_directories)
        assert result == [('Deployment', 'web'), ('Secret', 'web')]

    def test_definition_directories_used_are_only_the_repos_own_two_directories(self, tmp_path):
        deploy_dir = tmp_path / 'config' / 'kubernetes' / 'deploy'
        overrides_dir = tmp_path / 'config' / 'kubernetes' / 'development_overrides'
        deploy_dir.mkdir(parents=True)
        overrides_dir.mkdir(parents=True)
        command = FakeUndeployCommand(context(service_name='web'), project_dir=tmp_path)

        with mock.patch.object(undeploy.deploy, 'owned_objects', return_value=[]) as owned:
            command.targets

        owned.assert_called_once_with([deploy_dir, overrides_dir])


class TestConfirm:
    def test_not_required_inside_a_workspace_prints_nothing_and_never_prompts(self, capsys):
        command = FakeUndeployCommand(context(namespace='ws-example'))

        with mock.patch('builtins.input') as input_mock:
            command.confirm([('Secret', 'web')])

        input_mock.assert_not_called()
        assert capsys.readouterr().out == ''

    def test_lists_every_target_by_kind_and_name(self, capsys, kubectl_context_ok):
        command = FakeUndeployCommand(context(), yes=True)

        command.confirm([('Deployment', 'web'), ('Service', 'api')])

        output = capsys.readouterr().out
        assert 'Deployment/web' in output
        assert 'Service/api' in output

    def test_yes_flag_skips_the_prompt_without_touching_stdin(self, capsys, kubectl_context_ok):
        command = FakeUndeployCommand(context(), yes=True)

        with mock.patch.object(undeploy.sys, 'stdin') as stdin:
            command.confirm([('Secret', 'web')])

        stdin.isatty.assert_not_called()

    def test_non_tty_without_yes_is_refused(self, kubectl_context_ok):
        command = FakeUndeployCommand(context(), yes=False)

        with mock.patch.object(undeploy.sys, 'stdin', mock.Mock(**{'isatty.return_value': False})):
            with pytest.raises(undeploy.UndeployRefused) as excinfo:
                command.confirm([('Secret', 'web')])

        assert '--yes' in str(excinfo.value)

    def test_tty_accepts_lowercase_y(self, kubectl_context_ok):
        command = FakeUndeployCommand(context(), yes=False)

        with mock.patch.object(undeploy.sys, 'stdin', mock.Mock(**{'isatty.return_value': True})):
            with mock.patch('builtins.input', return_value='y'):
                command.confirm([('Secret', 'web')])  # must not raise

    def test_tty_accepts_yes_with_surrounding_whitespace_and_mixed_case(self, kubectl_context_ok):
        command = FakeUndeployCommand(context(), yes=False)

        with mock.patch.object(undeploy.sys, 'stdin', mock.Mock(**{'isatty.return_value': True})):
            with mock.patch('builtins.input', return_value='  YES  '):
                command.confirm([('Secret', 'web')])  # must not raise

    def test_tty_refuses_on_a_blank_answer(self, kubectl_context_ok):
        command = FakeUndeployCommand(context(), yes=False)

        with mock.patch.object(undeploy.sys, 'stdin', mock.Mock(**{'isatty.return_value': True})):
            with mock.patch('builtins.input', return_value=''):
                with pytest.raises(undeploy.UndeployRefused) as excinfo:
                    command.confirm([('Secret', 'web')])

        assert 'aborted' in str(excinfo.value).lower()

    def test_tty_refuses_on_explicit_no(self, kubectl_context_ok):
        command = FakeUndeployCommand(context(), yes=False)

        with mock.patch.object(undeploy.sys, 'stdin', mock.Mock(**{'isatty.return_value': True})):
            with mock.patch('builtins.input', return_value='n'):
                with pytest.raises(undeploy.UndeployRefused):
                    command.confirm([('Secret', 'web')])


class TestConfirmReportsTheTrueBlastRadius:
    """
    Critical 2: the confirmation listing must report where the deletion is
    actually going, not assert a fixed claim ("the shared environment") that
    nothing on screen could contradict. These deliberately mock
    preconditions.current_kubectl_context directly (not via kubectl_context_ok,
    which always returns 'minikube') so the test can prove the message is
    genuinely dynamic - not merely a differently-worded hardcoded string.
    """

    def test_header_names_the_actual_resolved_context(self, capsys):
        command = FakeUndeployCommand(context(), yes=True)

        with mock.patch.object(undeploy.preconditions, 'current_kubectl_context', return_value='gke-production'):
            command.confirm([('Secret', 'web')])

        assert 'gke-production' in capsys.readouterr().out

    def test_header_changes_with_whatever_context_is_actually_current(self, capsys):
        # Proves the message is not a fixed string with the context name
        # merely appended somewhere fixed - two different resolved contexts
        # must produce two different messages.
        first = FakeUndeployCommand(context(), yes=True)
        with mock.patch.object(undeploy.preconditions, 'current_kubectl_context', return_value='minikube'):
            first.confirm([('Secret', 'web')])
        first_output = capsys.readouterr().out

        second = FakeUndeployCommand(context(), yes=True)
        with mock.patch.object(undeploy.preconditions, 'current_kubectl_context', return_value='gke-production'):
            second.confirm([('Secret', 'web')])
        second_output = capsys.readouterr().out

        assert 'minikube' in first_output
        assert 'gke-production' not in first_output
        assert 'gke-production' in second_output
        assert 'minikube' not in second_output

    def test_header_never_makes_the_old_unqualified_shared_environment_claim(self, capsys):
        # The old wording asserted a destination ("the shared environment")
        # that nothing on screen could contradict. A reader must be told
        # what was actually found instead.
        command = FakeUndeployCommand(context(), yes=True)

        with mock.patch.object(undeploy.preconditions, 'current_kubectl_context', return_value='gke-production'):
            command.confirm([('Secret', 'web')])

        assert 'About to delete from the shared environment' not in capsys.readouterr().out

    def test_interactive_prompt_question_also_names_the_context(self):
        command = FakeUndeployCommand(context(), yes=False)

        with mock.patch.object(undeploy.preconditions, 'current_kubectl_context', return_value='gke-production'):
            with mock.patch.object(undeploy.sys, 'stdin', mock.Mock(**{'isatty.return_value': True})):
                with mock.patch('builtins.input', return_value='y') as input_mock:
                    command.confirm([('Secret', 'web')])

        prompt_text = input_mock.call_args.args[0]
        assert 'gke-production' in prompt_text


class TestRestoreAliases:
    def test_applies_only_owned_service_names_that_are_currently_shared(self, tmp_path):
        deploy_dir = tmp_path / 'config' / 'kubernetes' / 'deploy'
        deploy_dir.mkdir(parents=True)
        (deploy_dir / '01_service.yml').write_text('kind: Service\nmetadata:\n  name: api\n')
        (deploy_dir / '02_service.yml').write_text('kind: Service\nmetadata:\n  name: internal-only\n')
        command = FakeUndeployCommand(context(namespace='ws-example'), project_dir=tmp_path)

        with mock.patch.object(undeploy.aliases, 'list_shared_services', return_value={'api', 'billing'}):
            with mock.patch.object(undeploy.aliases, 'apply') as apply:
                command.restore_aliases()

        apply.assert_called_once_with('ws-example', ['api'])

    def test_does_not_apply_when_nothing_matches(self, tmp_path):
        deploy_dir = tmp_path / 'config' / 'kubernetes' / 'deploy'
        deploy_dir.mkdir(parents=True)
        (deploy_dir / '01_service.yml').write_text('kind: Service\nmetadata:\n  name: internal-only\n')
        command = FakeUndeployCommand(context(namespace='ws-example'), project_dir=tmp_path)

        with mock.patch.object(undeploy.aliases, 'list_shared_services', return_value={'api'}):
            with mock.patch.object(undeploy.aliases, 'apply') as apply:
                command.restore_aliases()

        apply.assert_not_called()

    def test_does_not_apply_when_repo_owns_no_services(self, tmp_path):
        command = FakeUndeployCommand(context(namespace='ws-example'), project_dir=tmp_path)

        with mock.patch.object(undeploy.aliases, 'list_shared_services', return_value={'api'}):
            with mock.patch.object(undeploy.aliases, 'apply') as apply:
                command.restore_aliases()

        apply.assert_not_called()


class TestRunProductionRefusal:
    """
    Safety property 1, exercised end to end: production must be refused by
    run() itself, before targets are computed or a single kubectl call is
    made - not merely by a helper that returns a boolean.
    """

    def test_run_raises_and_calls_kubectl_zero_times(self, tmp_path, kubectl_context_ok):
        # A workspace is active, so confirmation_required is False, and the
        # kubectl context is mocked to a valid one: the only possible source
        # of the raise is check_allowed itself, isolated from both confirm()'s
        # own (unrelated) non-TTY refusal and the kubectl-context guard.
        # Without this isolation, disabling check_allowed entirely would
        # still pass this test by accident, via one of those other guards.
        deploy_dir = tmp_path / 'config' / 'kubernetes' / 'deploy'
        deploy_dir.mkdir(parents=True)
        (deploy_dir / '01_service.yml').write_text('kind: Service\nmetadata:\n  name: api\n')
        command = FakeUndeployCommand(context(mode='production', namespace='ws-example'), project_dir=tmp_path)

        with mock.patch.object(undeploy.sh, 'kubectl') as kubectl:
            with mock.patch.object(undeploy.aliases, 'apply') as apply:
                with pytest.raises(undeploy.UndeployRefused):
                    command.run()

        kubectl.assert_not_called()
        apply.assert_not_called()

    def test_no_flag_or_context_value_overrides_the_refusal(self, tmp_path, kubectl_context_ok):
        # There is deliberately no "--force" or similar kwarg on UndeployCommand;
        # this test pins that yes=True cannot be (ab)used as one.
        command = FakeUndeployCommand(context(mode='production'), project_dir=tmp_path, yes=True)

        with mock.patch.object(undeploy.sh, 'kubectl') as kubectl:
            with pytest.raises(undeploy.UndeployRefused):
                command.run()

        kubectl.assert_not_called()


class TestRunKubectlContextGuard:
    """
    Critical 1: KUBEYARD_MODE is a machine-level setting with no relationship
    to which cluster kubectl currently points at. undeploy must independently
    verify the kubectl context before touching anything, in BOTH branches -
    including the workspace-active one, which previously had no guard at all.
    """

    def test_refuses_on_wrong_context_without_a_workspace(self, tmp_path):
        command = FakeUndeployCommand(context(), project_dir=tmp_path, yes=True)

        with mock.patch.object(undeploy.preconditions, 'current_kubectl_context', return_value='gke-production'):
            with mock.patch.object(undeploy.sh, 'kubectl') as kubectl:
                with pytest.raises(undeploy.preconditions.PreconditionFailed):
                    command.run()

        kubectl.assert_not_called()

    def test_refuses_on_wrong_context_with_a_workspace_active(self, tmp_path):
        # The finding this specifically closes: previously, a workspace-active
        # run skipped confirmation entirely and had no context check either -
        # a wrong context here would have issued a real, namespaced delete.
        deploy_dir = tmp_path / 'config' / 'kubernetes' / 'deploy'
        deploy_dir.mkdir(parents=True)
        (deploy_dir / '01_service.yml').write_text('kind: Service\nmetadata:\n  name: api\n')
        command = FakeUndeployCommand(context(namespace='ws-example'), project_dir=tmp_path)

        with mock.patch.object(undeploy.preconditions, 'current_kubectl_context', return_value='gke-production'):
            with mock.patch.object(undeploy.sh, 'kubectl') as kubectl:
                with mock.patch.object(undeploy.aliases, 'apply') as apply:
                    with pytest.raises(undeploy.preconditions.PreconditionFailed):
                        command.run()

        kubectl.assert_not_called()
        apply.assert_not_called()

    def test_checked_before_targets_are_computed_or_confirmed(self, tmp_path):
        deploy_dir = tmp_path / 'config' / 'kubernetes' / 'deploy'
        deploy_dir.mkdir(parents=True)
        (deploy_dir / '01_service.yml').write_text('kind: Service\nmetadata:\n  name: api\n')
        command = FakeUndeployCommand(context(), project_dir=tmp_path, yes=True)

        with mock.patch.object(undeploy.preconditions, 'current_kubectl_context', return_value='gke-production'):
            with mock.patch.object(undeploy.deploy, 'owned_objects') as owned_objects:
                with mock.patch('builtins.input') as input_mock:
                    with pytest.raises(undeploy.preconditions.PreconditionFailed):
                        command.run()

        owned_objects.assert_not_called()
        input_mock.assert_not_called()

    def test_passes_through_to_the_shared_helper_with_the_resolved_context(self, tmp_path):
        command = FakeUndeployCommand(context(namespace='ws-example'), project_dir=tmp_path)

        with mock.patch.object(undeploy.preconditions, 'current_kubectl_context', return_value='minikube'):
            with mock.patch.object(undeploy.preconditions, 'check_kubectl_context') as check_kubectl_context:
                with mock.patch.object(undeploy.sh, 'kubectl'):
                    with mock.patch.object(undeploy.aliases, 'apply'):
                        with mock.patch.object(undeploy.aliases, 'list_shared_services', return_value=set()):
                            command.run()

        check_kubectl_context.assert_called_once_with('minikube')


class TestRunInsideWorkspace:
    """Safety property 3: inside a workspace it just runs, and restores aliases."""

    def test_no_confirmation_prompt_and_kubectl_called_per_target_with_namespace(self, tmp_path, kubectl_context_ok):
        deploy_dir = tmp_path / 'config' / 'kubernetes' / 'deploy'
        deploy_dir.mkdir(parents=True)
        (deploy_dir / '01_service.yml').write_text('kind: Service\nmetadata:\n  name: api\n')
        command = FakeUndeployCommand(context(namespace='ws-example', service_name='web'), project_dir=tmp_path)

        with mock.patch.object(undeploy.sh, 'kubectl') as kubectl:
            with mock.patch('builtins.input') as input_mock:
                with mock.patch.object(undeploy.aliases, 'list_shared_services', return_value={'api'}):
                    with mock.patch.object(undeploy.aliases, 'apply') as apply:
                        command.run()

        input_mock.assert_not_called()
        assert kubectl.call_count == 2  # Service/api, Secret/web
        first_call, second_call = kubectl.call_args_list
        assert first_call.args == ('delete', 'service', 'api', '--namespace', 'ws-example', '--ignore-not-found')
        assert second_call.args == ('delete', 'secret', 'web', '--namespace', 'ws-example', '--ignore-not-found')
        apply.assert_called_once_with('ws-example', ['api'])

    def test_kubectl_delete_streams_stdout_but_leaves_stderr_for_sh_to_capture(self, tmp_path, kubectl_context_ok):
        """
        Redirecting _err would leave ErrorReturnCode.stderr empty, and
        delete_targets reads it to tell a missing resource type from a real
        failure - see TestUninstalledResourceTypeIsNotAFailure.
        """
        command = FakeUndeployCommand(context(namespace='ws-example'), project_dir=tmp_path)

        with mock.patch.object(undeploy.sh, 'kubectl') as kubectl:
            with mock.patch.object(undeploy.aliases, 'apply'):
                with mock.patch.object(undeploy.aliases, 'list_shared_services', return_value=set()):
                    command.run()

        assert kubectl.call_args.kwargs['_out'] is undeploy.sys.stdout.buffer
        assert '_err' not in kubectl.call_args.kwargs


class TestRunSharedEnvironment:
    """Safety property 2: the shared environment requires confirmation."""

    def test_tty_without_yes_prompts_and_proceeds_on_confirmation(self, tmp_path, kubectl_context_ok):
        command = FakeUndeployCommand(context(), project_dir=tmp_path, yes=False)

        with mock.patch.object(undeploy.sh, 'kubectl') as kubectl:
            with mock.patch.object(undeploy.sys, 'stdin', mock.Mock(**{'isatty.return_value': True})):
                with mock.patch('builtins.input', return_value='y') as input_mock:
                    command.run()

        input_mock.assert_called_once()
        kubectl.assert_called_once()
        # backward compatibility: no --namespace flag at all when inactive
        assert '--namespace' not in kubectl.call_args.args

    def test_non_tty_without_yes_is_refused_and_kubectl_is_never_called(self, tmp_path, kubectl_context_ok):
        # The core of safety property 2: an agent running non-interactively
        # must not be able to wipe the shared environment by accident.
        command = FakeUndeployCommand(context(), project_dir=tmp_path, yes=False)

        with mock.patch.object(undeploy.sh, 'kubectl') as kubectl:
            with mock.patch.object(undeploy.sys, 'stdin', mock.Mock(**{'isatty.return_value': False})):
                with pytest.raises(undeploy.UndeployRefused):
                    command.run()

        kubectl.assert_not_called()

    def test_non_tty_with_yes_proceeds_without_prompting(self, tmp_path, kubectl_context_ok):
        command = FakeUndeployCommand(context(), project_dir=tmp_path, yes=True)

        with mock.patch.object(undeploy.sh, 'kubectl') as kubectl:
            with mock.patch.object(undeploy.sys, 'stdin', mock.Mock(**{'isatty.return_value': False})):
                with mock.patch('builtins.input') as input_mock:
                    command.run()

        input_mock.assert_not_called()
        kubectl.assert_called_once()

    def test_aliases_are_never_restored_without_a_workspace(self, tmp_path, kubectl_context_ok):
        # Owns a Service that WOULD be restored as an alias if restore_aliases
        # ran - if run() called restore_aliases unconditionally instead of
        # gating it on self.namespace, this would catch it (an empty-repo
        # version of this test would not, since restore_aliases would be a
        # no-op either way).
        deploy_dir = tmp_path / 'config' / 'kubernetes' / 'deploy'
        deploy_dir.mkdir(parents=True)
        (deploy_dir / '01_service.yml').write_text('kind: Service\nmetadata:\n  name: api\n')
        command = FakeUndeployCommand(context(), project_dir=tmp_path, yes=True)

        with mock.patch.object(undeploy.sh, 'kubectl'):
            with mock.patch.object(undeploy.aliases, 'list_shared_services', return_value={'api'}):
                with mock.patch.object(undeploy.aliases, 'apply') as apply:
                    command.run()

        apply.assert_not_called()


class TestRunNothingToUndeploy:
    def test_logs_and_skips_kubectl_and_confirmation_when_there_are_no_targets(self, caplog, kubectl_context_ok):
        command = FakeUndeployCommand(context())

        with mock.patch.object(FakeUndeployCommand, 'targets', new_callable=mock.PropertyMock, return_value=[]):
            with mock.patch.object(undeploy.sh, 'kubectl') as kubectl:
                with mock.patch('builtins.input') as input_mock:
                    with caplog.at_level('INFO'):
                        command.run()

        kubectl.assert_not_called()
        input_mock.assert_not_called()
        assert any('nothing to undeploy' in record.message.lower() for record in caplog.records)


class TestDeleteTargetsPartialFailure:
    """
    Important: a delete that fails partway through must not abort the whole
    run, leave the workspace with neither a real Service nor a restored
    alias, or fail silently about which object is stuck.
    Compare DestroyWorkspaceCommand.delete_namespace, which has the same
    shape of fix for the same underlying problem (see
    tests/test_workspace_commands.py::TestDestroyWorkspaceCommandRun's
    "delete_failure" tests).
    """

    def _kubectl_side_effect(self, failing_args, error):
        def side_effect(*args, **kwargs):
            if args[:3] == failing_args:
                raise error
            return ''
        return side_effect

    def test_a_failing_delete_does_not_abort_the_remaining_deletes(self, tmp_path, kubectl_context_ok):
        deploy_dir = tmp_path / 'config' / 'kubernetes' / 'deploy'
        deploy_dir.mkdir(parents=True)
        (deploy_dir / '01_service.yml').write_text('kind: Service\nmetadata:\n  name: api\n')
        command = FakeUndeployCommand(context(namespace='ws-example', service_name='web'), project_dir=tmp_path)
        error = sh.ErrorReturnCode('kubectl', b'', b'Forbidden')

        with mock.patch.object(
                undeploy.sh, 'kubectl',
                side_effect=self._kubectl_side_effect(('delete', 'service', 'api'), error)) as kubectl:
            with mock.patch.object(undeploy.aliases, 'list_shared_services', return_value=set()):
                command.run()  # must not raise

        assert kubectl.call_count == 2  # both Service/api and Secret/web were attempted
        delete_kinds = [call.args[1] for call in kubectl.call_args_list]
        assert delete_kinds == ['service', 'secret']  # the second delete really ran, not skipped

    def test_aliases_are_still_restored_when_a_delete_fails(self, tmp_path, kubectl_context_ok):
        deploy_dir = tmp_path / 'config' / 'kubernetes' / 'deploy'
        deploy_dir.mkdir(parents=True)
        (deploy_dir / '01_service.yml').write_text('kind: Service\nmetadata:\n  name: api\n')
        command = FakeUndeployCommand(context(namespace='ws-example', service_name='web'), project_dir=tmp_path)
        error = sh.ErrorReturnCode('kubectl', b'', b'Forbidden')

        with mock.patch.object(
                undeploy.sh, 'kubectl',
                side_effect=self._kubectl_side_effect(('delete', 'service', 'api'), error)):
            with mock.patch.object(undeploy.aliases, 'list_shared_services', return_value={'api'}):
                with mock.patch.object(undeploy.aliases, 'apply') as apply:
                    command.run()  # must not raise

        apply.assert_called_once_with('ws-example', ['api'])

    def test_all_deletes_failing_still_restores_aliases(self, tmp_path, kubectl_context_ok):
        deploy_dir = tmp_path / 'config' / 'kubernetes' / 'deploy'
        deploy_dir.mkdir(parents=True)
        (deploy_dir / '01_service.yml').write_text('kind: Service\nmetadata:\n  name: api\n')
        command = FakeUndeployCommand(context(namespace='ws-example', service_name='web'), project_dir=tmp_path)
        error = sh.ErrorReturnCode('kubectl', b'', b'Forbidden')

        with mock.patch.object(undeploy.sh, 'kubectl', side_effect=error):
            with mock.patch.object(undeploy.aliases, 'list_shared_services', return_value={'api'}):
                with mock.patch.object(undeploy.aliases, 'apply') as apply:
                    with pytest.raises(undeploy.base_command.CommandException):
                        command.run()

        apply.assert_called_once_with('ws-example', ['api'])

    def test_a_partial_failure_is_still_not_fatal(self, tmp_path, kubectl_context_ok):
        # Deliberate asymmetry with the total-failure case below: the objects
        # that did go away really are gone, and the summary says which ones
        # are left, so the command has done something useful.
        deploy_dir = tmp_path / 'config' / 'kubernetes' / 'deploy'
        deploy_dir.mkdir(parents=True)
        (deploy_dir / '01_service.yml').write_text('kind: Service\nmetadata:\n  name: api\n')
        command = FakeUndeployCommand(context(namespace='ws-example', service_name='web'), project_dir=tmp_path)
        error = sh.ErrorReturnCode('kubectl', b'', b'Forbidden')

        with mock.patch.object(
                undeploy.sh, 'kubectl',
                side_effect=self._kubectl_side_effect(('delete', 'service', 'api'), error)):
            with mock.patch.object(undeploy.aliases, 'list_shared_services', return_value=set()):
                command.run()  # must not raise

    def test_failure_is_reported_by_kind_and_name_with_actionable_guidance(self, tmp_path, kubectl_context_ok, caplog):
        deploy_dir = tmp_path / 'config' / 'kubernetes' / 'deploy'
        deploy_dir.mkdir(parents=True)
        (deploy_dir / '01_service.yml').write_text('kind: Service\nmetadata:\n  name: api\n')
        command = FakeUndeployCommand(context(namespace='ws-example', service_name='web'), project_dir=tmp_path)
        error = sh.ErrorReturnCode('kubectl', b'', b'Forbidden')

        with mock.patch.object(
                undeploy.sh, 'kubectl',
                side_effect=self._kubectl_side_effect(('delete', 'service', 'api'), error)):
            with mock.patch.object(undeploy.aliases, 'list_shared_services', return_value=set()):
                with caplog.at_level('WARNING'):
                    command.run()

        messages = ' '.join(record.message for record in caplog.records)
        assert 'service/api' in messages.lower()  # names exactly which object failed
        assert 'undeploy' in messages.lower()  # tells the user how to retry

    def test_no_warning_at_all_when_every_delete_succeeds(self, tmp_path, kubectl_context_ok, caplog):
        command = FakeUndeployCommand(context(namespace='ws-example', service_name='web'), project_dir=tmp_path)

        with mock.patch.object(undeploy.sh, 'kubectl', return_value=''):
            with mock.patch.object(undeploy.aliases, 'list_shared_services', return_value=set()):
                with caplog.at_level('WARNING'):
                    command.run()

        assert caplog.records == []


class TestDeleteNothingIsNotSuccess:
    """
    Important: these commands exist so agents can script them, and an exit
    status of 0 after deleting nothing is the one outcome automation cannot
    recover from. Compare
    tests/test_workspace_commands.py::TestDestroyWorkspaceCommandRun, which
    pins the same decision for "workspace destroy".
    """

    def test_every_delete_failing_fails_the_command(self, tmp_path, kubectl_context_ok):
        command = FakeUndeployCommand(context(namespace='ws-example', service_name='web'), project_dir=tmp_path)
        error = sh.ErrorReturnCode('kubectl', b'', b'Forbidden')

        with mock.patch.object(undeploy.sh, 'kubectl', side_effect=error):
            with mock.patch.object(undeploy.aliases, 'list_shared_services', return_value=set()):
                with pytest.raises(undeploy.base_command.CommandException) as excinfo:
                    command.run()

        assert 'Secret/web' in str(excinfo.value)

    def test_the_failure_never_reports_a_successful_undeploy(self, tmp_path, kubectl_context_ok, caplog):
        command = FakeUndeployCommand(context(namespace='ws-example', service_name='web'), project_dir=tmp_path)
        error = sh.ErrorReturnCode('kubectl', b'', b'Forbidden')

        with mock.patch.object(undeploy.sh, 'kubectl', side_effect=error):
            with mock.patch.object(undeploy.aliases, 'list_shared_services', return_value=set()):
                with caplog.at_level('INFO'):
                    with pytest.raises(undeploy.base_command.CommandException):
                        command.run()

        assert not any('Undeployed 0 of' in record.message for record in caplog.records)
        assert not any(record.levelname == 'INFO' and 'Undeployed' in record.message for record in caplog.records)

    def test_report_result_is_silent_and_fatal_when_nothing_was_deleted(self):
        command = FakeUndeployCommand(context())
        targets = [('Service', 'api'), ('Secret', 'web')]

        with pytest.raises(undeploy.base_command.CommandException):
            command.report_result(targets, targets, [])


class TestUninstalledResourceTypeIsNotAFailure:
    """
    Found by the acceptance run, not by these tests: a cluster without the
    Prometheus operator has no PodMonitor or PrometheusRule resource type, so
    every such delete failed and the summary reported them as objects left
    behind. Nothing was left behind - the type does not exist, so neither can
    the objects. kubepy already skips the same custom resources when applying
    them, so such a cluster must undeploy as cleanly as it deploys.
    """

    MISSING_TYPE = b'error: the server doesn\'t have a resource type "podmonitor"\n'

    def _repo_with_a_custom_resource(self, tmp_path):
        deploy_dir = tmp_path / 'config' / 'kubernetes' / 'deploy'
        deploy_dir.mkdir(parents=True)
        (deploy_dir / '01_service.yml').write_text('kind: Service\nmetadata:\n  name: api\n')
        (deploy_dir / '02_pod_monitor.yml').write_text('kind: PodMonitor\nmetadata:\n  name: api\n')
        return FakeUndeployCommand(context(namespace='ws-example', service_name='web'), project_dir=tmp_path)

    def _kubectl_missing_podmonitor(self):
        def side_effect(*args, **kwargs):
            if args[1] == 'podmonitor':
                raise sh.ErrorReturnCode('kubectl', b'', self.MISSING_TYPE)
            return ''
        return side_effect

    def test_recognises_the_message_kubectl_uses(self):
        assert undeploy.is_uninstalled_resource_type(self.MISSING_TYPE)

    def test_does_not_swallow_an_ordinary_failure(self):
        assert not undeploy.is_uninstalled_resource_type(b'Error from server (Forbidden): pods is forbidden\n')

    def test_the_command_succeeds_and_never_calls_it_a_failure(self, tmp_path, kubectl_context_ok, caplog):
        command = self._repo_with_a_custom_resource(tmp_path)

        with mock.patch.object(undeploy.sh, 'kubectl', side_effect=self._kubectl_missing_podmonitor()):
            with mock.patch.object(undeploy.aliases, 'list_shared_services', return_value=set()):
                with caplog.at_level('WARNING'):
                    command.run()  # must not raise

        messages = ' '.join(record.message for record in caplog.records)
        assert 'failed' not in messages.lower()
        assert 'PodMonitor/api' in messages

    def test_skipped_objects_are_not_counted_as_undeployed(self, tmp_path, kubectl_context_ok, caplog):
        command = self._repo_with_a_custom_resource(tmp_path)

        with mock.patch.object(undeploy.sh, 'kubectl', side_effect=self._kubectl_missing_podmonitor()):
            with mock.patch.object(undeploy.aliases, 'list_shared_services', return_value=set()):
                with caplog.at_level('INFO'):
                    command.run()

        # Service/api and Secret/web really went away; PodMonitor/api never existed.
        assert any(record.message == 'Undeployed 2 objects.' for record in caplog.records)

    def test_a_real_failure_alongside_a_missing_type_is_still_a_failure(self, tmp_path, kubectl_context_ok):
        command = self._repo_with_a_custom_resource(tmp_path)

        def side_effect(*args, **kwargs):
            if args[1] == 'podmonitor':
                raise sh.ErrorReturnCode('kubectl', b'', self.MISSING_TYPE)
            raise sh.ErrorReturnCode('kubectl', b'', b'Forbidden')

        with mock.patch.object(undeploy.sh, 'kubectl', side_effect=side_effect):
            with mock.patch.object(undeploy.aliases, 'list_shared_services', return_value=set()):
                with pytest.raises(undeploy.base_command.CommandException) as excinfo:
                    command.run()

        assert 'Service/api' in str(excinfo.value)
        assert 'PodMonitor/api' not in str(excinfo.value)


class TestCliWiring:
    def test_undeploy_registered_with_yes_flag(self):
        result = CliRunner().invoke(cli, ['undeploy', '--help'])

        assert result.exit_code == 0
        assert '--yes' in result.output
        assert '-y' in result.output

    def test_undeploy_help_uses_the_command_docstring(self):
        result = CliRunner().invoke(cli, ['undeploy', '--help'])

        assert 'inverse of deploy' in result.output.lower()
