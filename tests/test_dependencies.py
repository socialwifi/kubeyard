from unittest import mock

import sh

from kubeyard import dependencies
from kubeyard.commands import dev_requirements


class TestNamespaceArguments:
    def test_pod_name_lookup_omits_namespace_when_inactive(self):
        dependency = dev_requirements.PostgresDependency()

        with mock.patch.object(dependencies.sh, 'kubectl', return_value='dev-postgres-1\n') as kubectl:
            dependency.pod_name

        assert '--namespace' not in kubectl.call_args[0]

    def test_pod_name_lookup_includes_namespace_when_active(self):
        dependency = dev_requirements.PostgresDependency('ws-example')

        with mock.patch.object(dependencies.sh, 'kubectl', return_value='dev-postgres-1\n') as kubectl:
            dependency.pod_name

        assert '--namespace' in kubectl.call_args[0]
        assert 'ws-example' in kubectl.call_args[0]

    def test_apply_and_expose_respect_namespace(self):
        dependency = dev_requirements.PostgresDependency()
        with mock.patch.object(dependencies.sh, 'kubectl') as kubectl:
            dependency._apply_definition()
        apply_call = [call for call in kubectl.call_args_list if call[0][0] == 'apply'][0]
        expose_call = [call for call in kubectl.call_args_list if call[0][0] == 'expose'][0]
        assert '--namespace' not in apply_call[0]
        assert '--namespace' not in expose_call[0]

        dependency = dev_requirements.PostgresDependency('ws-example')
        with mock.patch.object(dependencies.sh, 'kubectl') as kubectl:
            dependency._apply_definition()
        apply_call = [call for call in kubectl.call_args_list if call[0][0] == 'apply'][0]
        expose_call = [call for call in kubectl.call_args_list if call[0][0] == 'expose'][0]
        assert '--namespace' in apply_call[0]
        assert 'ws-example' in apply_call[0]
        assert '--namespace' in expose_call[0]
        assert 'ws-example' in expose_call[0]

    def test_wait_for_started_log_respects_namespace(self):
        dependency = dev_requirements.PostgresDependency()
        with mock.patch.object(dependencies.sh, 'kubectl', return_value=[dependency.started_log]) as kubectl:
            dependency._wait_for_started_log()
        assert '--namespace' not in kubectl.call_args[0]

        dependency = dev_requirements.PostgresDependency('ws-example')
        with mock.patch.object(dependencies.sh, 'kubectl', return_value=[dependency.started_log]) as kubectl:
            dependency._wait_for_started_log()
        assert '--namespace' in kubectl.call_args[0]
        assert 'ws-example' in kubectl.call_args[0]

    def test_is_container_running_respects_namespace(self):
        dependency = dev_requirements.PostgresDependency()
        with mock.patch.object(dependencies.sh, 'kubectl', return_value='"true"') as kubectl:
            assert dependency.is_container_running() is True
        assert '--namespace' not in kubectl.call_args[0]

        dependency = dev_requirements.PostgresDependency('ws-example')
        with mock.patch.object(dependencies.sh, 'kubectl', return_value='"true"') as kubectl:
            assert dependency.is_container_running() is True
        assert '--namespace' in kubectl.call_args[0]
        assert 'ws-example' in kubectl.call_args[0]

    def test_run_command_respects_namespace(self):
        dependency = dev_requirements.PostgresDependency()
        with mock.patch.object(dependencies.sh, 'kubectl', return_value='pod-1') as kubectl:
            dependency.run_command('echo', 'hi')
        exec_call = [call for call in kubectl.call_args_list if call[0][0] == 'exec'][0]
        assert '--namespace' not in exec_call[0]

        dependency = dev_requirements.PostgresDependency('ws-example')
        with mock.patch.object(dependencies.sh, 'kubectl', return_value='pod-1') as kubectl:
            dependency.run_command('echo', 'hi')
        exec_call = [call for call in kubectl.call_args_list if call[0][0] == 'exec'][0]
        assert '--namespace' in exec_call[0]
        assert 'ws-example' in exec_call[0]


def error(stderr):
    return sh.ErrorReturnCode('createdb', b'', stderr)


class TestEnsureDatabasePresent:
    def test_returns_true_when_database_created(self):
        dependency = dev_requirements.PostgresDependency()

        with mock.patch.object(dependency, 'run_command', return_value=''):
            assert dependency.ensure_database_present('web') is True

    def test_returns_false_when_database_already_exists(self):
        dependency = dev_requirements.PostgresDependency()

        with mock.patch.object(dependency, 'run_command', side_effect=error(b'database already exists')):
            assert dependency.ensure_database_present('web') is False

    def test_reraises_unexpected_errors(self):
        dependency = dev_requirements.PostgresDependency()

        with mock.patch.object(dependency, 'run_command', side_effect=error(b'connection refused')):
            try:
                dependency.ensure_database_present('web')
            except sh.ErrorReturnCode:
                pass
            else:
                raise AssertionError('expected ErrorReturnCode to propagate')


class FakeRequirementCommand:
    def __init__(self, created):
        self.created = created

    def __call__(self, arguments):
        return self.created


class TestRequirementsDispatcher:
    def test_dispatch_all_returns_true_if_any_requirement_created_database(self):
        dispatcher = dev_requirements.RequirementsDispatcher({})
        dispatcher.commands = {
            'creates': lambda context: FakeRequirementCommand(True),
            'no-op': lambda context: FakeRequirementCommand(False),
        }

        result = dispatcher.dispatch_all([{'kind': 'no-op'}, {'kind': 'creates'}])

        assert result is True

    def test_dispatch_all_returns_false_if_nothing_created(self):
        dispatcher = dev_requirements.RequirementsDispatcher({})
        dispatcher.commands = {
            'no-op': lambda context: FakeRequirementCommand(False),
        }

        result = dispatcher.dispatch_all([{'kind': 'no-op'}, {'kind': 'no-op'}])

        assert result is False

    def test_dispatch_returns_false_for_unsupported_kind(self):
        dispatcher = dev_requirements.RequirementsDispatcher({})
        dispatcher.commands = {}

        assert dispatcher.dispatch({'kind': 'unknown'}) is False

    def test_dispatch_all_handles_unsupported_kind_without_raising(self):
        dispatcher = dev_requirements.RequirementsDispatcher({})
        dispatcher.commands = {
            'creates': lambda context: FakeRequirementCommand(True),
        }

        result = dispatcher.dispatch_all([{'kind': 'unsupported'}, {'kind': 'creates'}])

        assert result is True

    def test_dispatch_all_skips_requirement_without_kind(self):
        dispatcher = dev_requirements.RequirementsDispatcher({})
        dispatcher.commands = {
            'creates': lambda context: FakeRequirementCommand(True),
        }

        result = dispatcher.dispatch_all([{'no-kind-here': True}, {'kind': 'creates'}])

        assert result is True
