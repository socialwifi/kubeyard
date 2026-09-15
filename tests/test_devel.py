from kubeyard.commands import devel
from kubeyard.commands import test as test_command


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


def make_test_database(ctx, tag):
    """Build the real database object the test command would use, nothing else mocked out."""
    return test_command.PostgresDatabase(
        is_development=True,
        volumes=(),
        context=ctx,
        tag=tag,
        docker_runner=None,
        tested_image_name='web',
    )


class TestDefaultTag:
    def test_development_without_workspace_is_dev(self):
        assert FakeDevelCommand(context()).default_tag == 'dev'

    def test_development_with_workspace_is_suffixed(self):
        assert FakeDevelCommand(context(workspace='example')).default_tag == 'dev-example'

    def test_production_is_latest_even_with_workspace(self):
        assert FakeDevelCommand(context(mode='production', workspace='example')).default_tag == 'latest'

    def test_tag_flows_into_test_database_container_name(self):
        # Two workspaces must not share a test-database container, so this has
        # to read the real container_name off the real database class rather
        # than rebuild the string it expects.
        command = FakeDevelCommand(context(workspace='example'))

        database = make_test_database(command.context, tag=command.tag)

        assert command.tag == 'dev-example'
        assert database.container_name == 'db-test-web-dev-example'

    def test_two_workspaces_get_different_test_database_containers(self):
        one = FakeDevelCommand(context(workspace='example'))
        other = FakeDevelCommand(context(workspace='other'))

        names = {
            make_test_database(command.context, tag=command.tag).container_name
            for command in (one, other)
        }

        assert len(names) == 2
