from unittest import mock

from kubeyard.commands import devel
from kubeyard.commands import test as test_command
from kubeyard.entrypoints import kubeyard as entrypoint


class TestForwardedArguments:
    def forwarded(self, argv):
        with mock.patch.object(devel.sys, 'argv', argv):
            return devel.BaseDevelCommand.args.fget(mock.Mock())

    def test_the_command_line_reaches_the_script(self):
        assert self.forwarded(['kubeyard', 'deploy', '--tag', '630']) == ['--tag', '630']

    def test_nothing_given_forwards_nothing(self):
        assert self.forwarded(['kubeyard', 'deploy']) == []

    def test_values_containing_spaces_stay_one_argument(self):
        argv = ['kubeyard', 'deploy', '--build-url', 'https://ci/a b/']
        assert self.forwarded(argv) == ['--build-url', 'https://ci/a b/']


def test_nothing_can_precede_the_command_name():
    """`args` slices sys.argv after the command, so a group option taking a value would break it."""
    assert all(param.is_eager and not param.expose_value for param in entrypoint.cli.params)


def test_a_test_script_is_given_the_runners_arguments_only():
    """Those scripts end in `run_tests "$@"`, so kubeyard's own options must not appear there."""
    assert 'args' in vars(test_command.TestCommand)
