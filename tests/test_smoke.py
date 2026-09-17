from kubeyard import settings


class TestPackageImports:
    def test_settings_expose_defaults(self):
        assert settings.DEFAULT_KUBEYARD_CONTEXT_FILEPATH == 'config/kubeyard.yml'
        assert settings.DEFAULT_KUBERNETES_DEPLOY_DIR == 'config/kubernetes/deploy'
