from unittest import mock

import pytest

from kubeyard import kubernetes
from kubeyard import settings


def context(namespace=''):
    return {
        'KUBEYARD_MODE': 'development',
        'KUBEYARD_NAMESPACE': namespace,
        'KUBE_SERVICE_NAME': 'web',
        'PROJECT_DIR': '/tmp/project',
        'KUBERNETES_DEV_SECRETS_DIR': 'config/kubernetes/dev_secrets',
    }


class TestSecretsInstallerNamespace:
    def test_no_namespace_flag_when_workspace_inactive(self):
        installer = kubernetes.DevelopmentKubernetesSecretsInstaller(context())

        mock_manipulator = mock.Mock()
        mock_manipulator.get_literal_secrets.return_value = [('key', 'value')]
        mock_manipulator.get_file_secrets.return_value = []

        with mock.patch.object(kubernetes.sh, 'kubectl') as kubectl:
            with mock.patch.object(type(installer), 'manipulator', new_callable=mock.PropertyMock) as mock_prop:
                mock_prop.return_value = mock_manipulator
                installer.install()

        first_call_args = kubectl.call_args_list[0][0]
        assert '--namespace' not in first_call_args

    def test_namespace_flag_when_workspace_active(self):
        installer = kubernetes.DevelopmentKubernetesSecretsInstaller(context('ws-example'))

        mock_manipulator = mock.Mock()
        mock_manipulator.get_literal_secrets.return_value = [('key', 'value')]
        mock_manipulator.get_file_secrets.return_value = []

        with mock.patch.object(kubernetes.sh, 'kubectl') as kubectl:
            with mock.patch.object(type(installer), 'manipulator', new_callable=mock.PropertyMock) as mock_prop:
                mock_prop.return_value = mock_manipulator
                installer.install()

        first_call_args = kubectl.call_args_list[0][0]
        assert '--namespace' in first_call_args
        assert 'ws-example' in first_call_args


class TestIsKeyPresentNamespace:
    def test_no_namespace_flag_when_inactive(self):
        manipulator = kubernetes.KubernetesSecretsManipulator('redis-urls', '/tmp', namespace='')

        with mock.patch.object(kubernetes.sh, 'kubectl', return_value='data: {}\n') as kubectl:
            manipulator.is_key_present('web')

        assert '--namespace' not in kubectl.call_args[0]

    def test_namespace_flag_when_active(self):
        manipulator = kubernetes.KubernetesSecretsManipulator('redis-urls', '/tmp', namespace='ws-example')

        with mock.patch.object(kubernetes.sh, 'kubectl', return_value='data: {}\n') as kubectl:
            manipulator.is_key_present('web')

        assert '--namespace' in kubectl.call_args[0]


class TestContextSetupNamespace:
    def test_configmap_created_without_namespace_when_inactive(self):
        setup = kubernetes.ProductionKubernetesContext()

        with mock.patch.object(kubernetes.sh, 'kubectl') as kubectl:
            setup.setup()

        create_call = [call for call in kubectl.call_args_list if call[0][0] == 'create'][0]
        assert '--namespace' not in create_call[0]


class FakeCluster:
    pass


class FakeClusterFactory:
    def get(self, context):
        return FakeCluster()


@pytest.fixture
def development_context(monkeypatch):
    monkeypatch.setattr(kubernetes.minikube, 'ClusterFactory', lambda: FakeClusterFactory())
    return kubernetes.DevelopmentKubernetesContext


class TestBaseDomain:
    def test_base_domain_defaults_to_the_dev_tld(self, development_context):
        context = development_context({'DEV_TLD': 'testing'})
        assert context.base_domain == 'testing'

    def test_base_domain_follows_a_configured_dev_tld(self, development_context):
        context = development_context({'DEV_TLD': 'example.test'})
        assert context.base_domain == 'example.test'

    def test_base_domain_is_qualified_inside_a_workspace(self, development_context):
        context = development_context({'DEV_TLD': 'example.test'}, namespace='ws-chosen')
        assert context.base_domain == 'chosen.ws.example.test'

    def test_base_domain_ignores_a_namespace_that_is_not_a_workspace(self, development_context):
        context = development_context({'DEV_TLD': 'example.test'}, namespace='default')
        assert context.base_domain == 'example.test'

    def test_base_domain_falls_back_when_the_context_has_no_dev_tld(self, development_context):
        """`kubeyard setup` builds this from the global context, which carries no DEV_TLD."""
        context = development_context({})
        assert context.base_domain == settings.DEFAULT_DEV_TLD
