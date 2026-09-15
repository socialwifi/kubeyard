from kubeyard.commands import devel


class FakeDevelCommand(devel.BaseDevelCommand):
    custom_script_name = 'fake'

    def __init__(self, context):
        self._context = context
        self._tag = None
        self._image_name = None

    @property
    def context(self):
        return self._context


def context(mode='development', workspace=''):
    return {
        'KUBEYARD_MODE': mode,
        'KUBEYARD_WORKSPACE': workspace,
        'DOCKER_IMAGE_NAME': 'web',
    }


class TestDefaultTag:
    def test_development_without_workspace_is_dev(self):
        assert FakeDevelCommand(context()).default_tag == 'dev'

    def test_development_with_workspace_is_suffixed(self):
        assert FakeDevelCommand(context(workspace='example')).default_tag == 'dev-example'

    def test_production_is_latest_even_with_workspace(self):
        assert FakeDevelCommand(context(mode='production', workspace='example')).default_tag == 'latest'

    def test_tag_flows_into_test_database_container_name(self):
        command = FakeDevelCommand(context(workspace='example'))

        container_name = 'db-test-{}-{}'.format(
            command.context['DOCKER_IMAGE_NAME'], command.tag)

        assert container_name == 'db-test-web-dev-example'
