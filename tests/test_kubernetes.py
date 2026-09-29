from unittest import mock

import pytest

from kubeyard import context_factories
from kubeyard import kubernetes


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
        setup = kubernetes.ProductionKubernetesContext({'BASE_DOMAIN': 'example.com'})

        with mock.patch.object(kubernetes, 'sh') as sh:
            sh.kubectl.get.configmap.side_effect = FakeErrorReturnCode()
            sh.ErrorReturnCode = FakeErrorReturnCode
            setup.setup()

        create_call = [call for call in sh.kubectl.call_args_list if call[0][0] == 'create'][0]
        assert '--namespace' not in create_call[0]


class FakeErrorReturnCode(Exception):
    pass


class TestProductionConfigMapIsNotOverwritten:
    def production(self):
        return kubernetes.ProductionKubernetesContext({'BASE_DOMAIN': 'example.com'})

    def test_existing_configmap_is_left_alone(self):
        with mock.patch.object(kubernetes, 'sh') as sh:
            sh.kubectl.get.configmap.return_value = '{"data": {"base-domain": "example.com"}}'
            self.production().setup()

        assert not [call for call in sh.kubectl.call_args_list if call[0][0] == 'create']

    def test_replace_flag_overwrites_it(self):
        with mock.patch.object(kubernetes, 'sh') as sh:
            sh.kubectl.get.configmap.return_value = '{"data": {"base-domain": "example.com"}}'
            self.production().setup(replace_configmap=True)

        assert [call for call in sh.kubectl.call_args_list if call[0][0] == 'create']

    def test_development_always_rewrites_it(self, development_context):
        context = development_context({'BASE_DOMAIN': 'example.test'})

        with mock.patch.object(kubernetes, 'sh') as sh:
            sh.kubectl.get.configmap.return_value = '{"data": {"base-domain": "stale"}}'
            context.setup()

        assert [call for call in sh.kubectl.call_args_list if call[0][0] == 'create']


class FakeCluster:
    def ensure_started(self):
        pass


class FakeClusterFactory:
    def get(self, context):
        return FakeCluster()


@pytest.fixture
def development_context(monkeypatch):
    monkeypatch.setattr(kubernetes.minikube, 'ClusterFactory', lambda: FakeClusterFactory())
    return kubernetes.DevelopmentKubernetesContext


class TestBaseDomain:
    def test_base_domain_is_the_configured_one(self, development_context):
        context = development_context({'BASE_DOMAIN': 'example.test'})
        assert context.base_domain == 'example.test'

    def test_base_domain_is_qualified_inside_a_workspace(self, development_context):
        context = development_context({'BASE_DOMAIN': 'example.test'}, namespace='ws-chosen')
        assert context.base_domain == 'chosen.ws.example.test'

    def test_base_domain_ignores_a_namespace_that_is_not_a_workspace(self, development_context):
        context = development_context({'BASE_DOMAIN': 'example.test'}, namespace='default')
        assert context.base_domain == 'example.test'

    def test_unset_base_domain_is_an_error_rather_than_an_invented_domain(self, development_context):
        with pytest.raises(context_factories.ConfigurationError):
            development_context({}).base_domain

    def test_production_base_domain_is_configured_not_hardcoded(self):
        assert kubernetes.ProductionKubernetesContext({'BASE_DOMAIN': 'example.com'}).base_domain == 'example.com'
