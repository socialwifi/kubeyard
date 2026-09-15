from unittest import mock

import pytest
import sh

from kubeyard.commands import seed

PODS = [
    'web-7d9f8b5c4-abcde',
    'web-api-6c8f7a4b3-fghij',
]


class TestSelectPod:
    def test_prefix_match_returns_shortest_name(self):
        assert seed.select_pod(PODS, 'web') == 'web-7d9f8b5c4-abcde'

    def test_more_specific_prefix_selects_the_api_pod(self):
        assert seed.select_pod(PODS, 'web-api') == 'web-api-6c8f7a4b3-fghij'

    def test_exact_match_wins(self):
        assert seed.select_pod(PODS + ['seeder'], 'seeder') == 'seeder'

    def test_raises_when_nothing_matches(self):
        with pytest.raises(seed.SeedError) as excinfo:
            seed.select_pod(PODS, 'accounts')

        assert 'accounts' in str(excinfo.value)

    def test_raises_on_empty_pod_list(self):
        with pytest.raises(seed.SeedError):
            seed.select_pod([], 'web')

    def test_multiple_equally_short_matches_logs_a_warning_and_picks_one(self):
        # Two pods of identical length both match the prefix: select_pod must
        # not raise (it degrades to a deterministic choice), but it should
        # tell the operator the match was ambiguous.
        pods = ['web-aaaaa', 'web-bbbbb']

        with mock.patch.object(seed.logger, 'warning') as warning:
            result = seed.select_pod(pods, 'web')

        assert result in pods
        warning.assert_called_once()


class TestTargetPodName:
    def test_defaults_to_kube_service_name(self):
        runner = seed.SeedRunner({'KUBE_SERVICE_NAME': 'web'})

        assert runner.target == 'web'

    def test_dev_seed_pod_overrides(self):
        runner = seed.SeedRunner({'KUBE_SERVICE_NAME': 'web', 'DEV_SEED_POD': 'web-api'})

        assert runner.target == 'web-api'


class TestNamespaceArgs:
    def test_no_namespace_flag_when_inactive(self):
        runner = seed.SeedRunner({'KUBEYARD_NAMESPACE': ''})

        assert runner.namespace_args == ()

    def test_namespace_flag_when_active(self):
        runner = seed.SeedRunner({'KUBEYARD_NAMESPACE': 'ws-example'})

        assert runner.namespace_args == ('--namespace', 'ws-example')


class TestCommand:
    def test_splits_the_configured_shell_command(self):
        runner = seed.SeedRunner({'DEV_SEED_COMMAND': 'python -m tests.demo'})

        assert runner.command == ['python', '-m', 'tests.demo']


class TestWaitForRollout:
    def test_no_namespace_flag_when_inactive(self):
        runner = seed.SeedRunner({'KUBEYARD_NAMESPACE': ''})

        with mock.patch.object(seed.sh, 'kubectl') as kubectl:
            runner.wait_for_rollout(['web'])

        kubectl.assert_called_once()
        args = kubectl.call_args.args
        assert args[:2] == ('rollout', 'status')
        assert args[2] == 'deployment/web'
        assert '--namespace' not in args
        assert '--timeout' in args
        assert seed.ROLLOUT_TIMEOUT in args

    def test_namespace_flag_when_active(self):
        runner = seed.SeedRunner({'KUBEYARD_NAMESPACE': 'ws-example'})

        with mock.patch.object(seed.sh, 'kubectl') as kubectl:
            runner.wait_for_rollout(['web'])

        args = kubectl.call_args.args
        assert '--namespace' in args
        assert 'ws-example' in args

    def test_waits_for_every_deployment_in_order(self):
        runner = seed.SeedRunner({'KUBEYARD_NAMESPACE': ''})

        with mock.patch.object(seed.sh, 'kubectl') as kubectl:
            runner.wait_for_rollout(['web', 'migrate'])

        assert kubectl.call_count == 2
        assert kubectl.call_args_list[0].args[2] == 'deployment/web'
        assert kubectl.call_args_list[1].args[2] == 'deployment/migrate'

    def test_timeout_is_raised_as_seed_error_naming_the_deployment(self):
        # A rollout timeout must not surface as a bare sh.ErrorReturnCode: that
        # exception type is also raised by install_secrets, by kubepy's
        # apply_all, and by every other kubectl call in the codebase, so an
        # unwrapped error is indistinguishable from an unrelated deploy failure.
        runner = seed.SeedRunner({'KUBEYARD_NAMESPACE': ''})
        error = sh.ErrorReturnCode('kubectl', b'', b'timed out waiting for the condition')

        with mock.patch.object(seed.sh, 'kubectl', side_effect=error):
            with pytest.raises(seed.SeedError) as excinfo:
                runner.wait_for_rollout(['web'])

        assert 'web' in str(excinfo.value)
        assert excinfo.value.__cause__ is error


class TestPodNames:
    def test_no_namespace_flag_when_inactive(self):
        runner = seed.SeedRunner({'KUBEYARD_NAMESPACE': ''})

        with mock.patch.object(seed.sh, 'kubectl', return_value='web-abc123') as kubectl:
            assert runner.pod_names() == ['web-abc123']

        args = kubectl.call_args.args
        assert '--namespace' not in args
        assert args[:2] == ('get', 'pods')

    def test_namespace_flag_when_active(self):
        runner = seed.SeedRunner({'KUBEYARD_NAMESPACE': 'ws-example'})

        with mock.patch.object(seed.sh, 'kubectl', return_value='web-abc123') as kubectl:
            runner.pod_names()

        args = kubectl.call_args.args
        assert '--namespace' in args
        assert 'ws-example' in args

    def test_empty_output_yields_no_pods(self):
        runner = seed.SeedRunner({'KUBEYARD_NAMESPACE': ''})

        with mock.patch.object(seed.sh, 'kubectl', return_value=''):
            assert runner.pod_names() == []

    def test_multiple_pods_are_split_on_whitespace(self):
        runner = seed.SeedRunner({'KUBEYARD_NAMESPACE': ''})

        with mock.patch.object(seed.sh, 'kubectl', return_value='web-abc123 web-def456'):
            assert runner.pod_names() == ['web-abc123', 'web-def456']


class TestSeed:
    def test_execs_the_configured_command_in_the_selected_pod(self):
        runner = seed.SeedRunner({
            'KUBEYARD_NAMESPACE': '', 'KUBE_SERVICE_NAME': 'web', 'DEV_SEED_COMMAND': 'python -m tests.demo',
        })

        with mock.patch.object(runner, 'pod_names', return_value=['web-abc123']):
            with mock.patch.object(seed.sh, 'kubectl') as kubectl:
                runner.seed()

        args = kubectl.call_args.args
        assert args[0] == 'exec'
        assert args[1] == 'web-abc123'
        assert '--' in args
        dash_index = args.index('--')
        assert list(args[dash_index + 1:]) == ['python', '-m', 'tests.demo']

    def test_namespace_flag_is_forwarded_to_exec(self):
        runner = seed.SeedRunner({
            'KUBEYARD_NAMESPACE': 'ws-example', 'KUBE_SERVICE_NAME': 'web', 'DEV_SEED_COMMAND': 'seed',
        })

        with mock.patch.object(runner, 'pod_names', return_value=['web-abc123']):
            with mock.patch.object(seed.sh, 'kubectl') as kubectl:
                runner.seed()

        args = kubectl.call_args.args
        assert '--namespace' in args
        assert 'ws-example' in args

    def test_exec_failure_is_raised_as_seed_error_naming_the_pod(self):
        # Same reasoning as the rollout case: a failed exec must not surface
        # as a bare sh.ErrorReturnCode, indistinguishable from any other
        # kubectl failure in the deploy path.
        runner = seed.SeedRunner({
            'KUBEYARD_NAMESPACE': '', 'KUBE_SERVICE_NAME': 'web', 'DEV_SEED_COMMAND': 'python -m tests.demo',
        })
        error = sh.ErrorReturnCode('kubectl', b'', b'command terminated with exit code 1')

        with mock.patch.object(runner, 'pod_names', return_value=['web-abc123']):
            with mock.patch.object(seed.sh, 'kubectl', side_effect=error):
                with pytest.raises(seed.SeedError) as excinfo:
                    runner.seed()

        assert 'web-abc123' in str(excinfo.value)
        assert excinfo.value.__cause__ is error


class TestWaitAndSeed:
    def test_waits_for_rollout_before_seeding(self):
        runner = seed.SeedRunner({'KUBEYARD_NAMESPACE': ''})
        manager = mock.Mock()
        with mock.patch.object(runner, 'wait_for_rollout', manager.wait_for_rollout):
            with mock.patch.object(runner, 'seed', manager.seed):
                runner.wait_and_seed(['web'])

        assert manager.mock_calls == [
            mock.call.wait_for_rollout(['web']),
            mock.call.seed(),
        ]


class TestSeedCommand:
    def make_command(self):
        return seed.SeedCommand.__new__(seed.SeedCommand)

    def test_raises_when_seed_command_is_not_configured(self):
        command = self.make_command()

        with mock.patch.object(seed.base_command.InitialisedRepositoryCommand, 'run'):
            with mock.patch.object(seed.SeedCommand, 'context', new_callable=mock.PropertyMock, return_value={}):
                with pytest.raises(seed.base_command.CommandException):
                    command.run()

    def test_seeds_when_configured(self):
        command = self.make_command()

        with mock.patch.object(seed.base_command.InitialisedRepositoryCommand, 'run'):
            with mock.patch.object(
                    seed.SeedCommand, 'context', new_callable=mock.PropertyMock,
                    return_value={'DEV_SEED_COMMAND': 'python -m tests.demo'}):
                with mock.patch.object(seed, 'SeedRunner') as seed_runner_cls:
                    command.run()

        seed_runner_cls.return_value.seed.assert_called_once()
