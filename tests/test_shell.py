from unittest import mock

from kubeyard.commands import shell


class FakeShellCommand(shell.ShellCommand):
    """
    Bypasses BaseDevelCommand.__init__, which would start minikube.
    """

    def __init__(self, context, *, shell='/bin/sh', pod=None, container=None, root=True):
        self._context = context
        self.shell = shell
        self.pod = pod
        self.container = container
        self.root = root
        self._tag = None
        self._image_name = None

    @property
    def context(self):
        return self._context


def context(namespace=''):
    return {
        'KUBEYARD_NAMESPACE': namespace,
        'DOCKER_IMAGE_NAME': 'web',
    }


class TestPodNameByImageLookupNamespace:
    def test_no_namespace_flag_when_inactive(self):
        command = FakeShellCommand(context())

        with mock.patch.object(shell.sh, 'kubectl') as kubectl:
            kubectl.get.pods.return_value = ['web-abc123 1/1 Running']
            assert command.pod_name == 'web-abc123'

        assert '--namespace' not in kubectl.get.pods.call_args[0]

    def test_namespace_flag_when_active(self):
        command = FakeShellCommand(context('ws-example'))

        with mock.patch.object(shell.sh, 'kubectl') as kubectl:
            kubectl.get.pods.return_value = ['web-abc123 1/1 Running']
            assert command.pod_name == 'web-abc123'

        assert '--namespace' in kubectl.get.pods.call_args[0]
        assert 'ws-example' in kubectl.get.pods.call_args[0]


class TestPodNameByExplicitPodNamespace:
    def test_no_namespace_flag_when_inactive(self):
        command = FakeShellCommand(context(), pod='pod-1')

        with mock.patch.object(shell.sh, 'kubectl') as kubectl:
            kubectl.get.pods.return_value = 'pod-1 pod-2'
            assert command.pod_name == 'pod-1'

        assert '--namespace' not in kubectl.get.pods.call_args[0]

    def test_namespace_flag_when_active(self):
        command = FakeShellCommand(context('ws-example'), pod='pod-1')

        with mock.patch.object(shell.sh, 'kubectl') as kubectl:
            kubectl.get.pods.return_value = 'pod-1 pod-2'
            assert command.pod_name == 'pod-1'

        assert '--namespace' in kubectl.get.pods.call_args[0]
        assert 'ws-example' in kubectl.get.pods.call_args[0]


class TestRunDefaultNamespace:
    """
    root=True: after_command is empty, so run_default makes a single exec
    call (the interactive shell).
    """

    def test_no_namespace_flag_when_inactive(self):
        command = FakeShellCommand(context(), container='app', root=True)
        command.pod_name = 'pod-1'

        with mock.patch.object(shell.sh, 'kubectl') as kubectl:
            command.run_default()

        assert '--namespace' not in kubectl.exec.call_args[0]

    def test_namespace_flag_when_active(self):
        command = FakeShellCommand(context('ws-example'), container='app', root=True)
        command.pod_name = 'pod-1'

        with mock.patch.object(shell.sh, 'kubectl') as kubectl:
            command.run_default()

        assert '--namespace' in kubectl.exec.call_args[0]
        assert 'ws-example' in kubectl.exec.call_args[0]


class TestRunDefaultCleanupExecNamespace:
    """
    root=False (the CLI default: --root is a bare is_flag with no
    default=True) makes after_command non-empty, so run_default makes TWO
    exec calls: the interactive shell, then the finally-block cleanup. Both
    must independently carry the namespace.
    """

    def make_command(self, namespace):
        command = FakeShellCommand(context(namespace), container='app', root=False)
        command.pod_name = 'pod-1'
        command.uid = '1000'
        command.gid = '1000'
        command.username = 'tester'
        return command

    def test_no_namespace_flag_when_inactive(self):
        command = self.make_command('')

        with mock.patch.object(shell.sh, 'kubectl') as kubectl:
            command.run_default()

        assert kubectl.exec.call_count == 2
        first_call, second_call = kubectl.exec.call_args_list
        assert '--namespace' not in first_call[0]
        assert '--namespace' not in second_call[0]

    def test_namespace_flag_when_active(self):
        command = self.make_command('ws-example')

        with mock.patch.object(shell.sh, 'kubectl') as kubectl:
            command.run_default()

        assert kubectl.exec.call_count == 2
        first_call, second_call = kubectl.exec.call_args_list
        assert '--namespace' in first_call[0]
        assert 'ws-example' in first_call[0]
        assert '--namespace' in second_call[0]
        assert 'ws-example' in second_call[0]
