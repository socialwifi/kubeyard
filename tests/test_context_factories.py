import pathlib

import pytest
import yaml

from kubeyard import context_factories


@pytest.fixture
def project_dir(tmp_path):
    config = tmp_path / 'config'
    config.mkdir()
    (config / 'kubeyard.yml').write_text(yaml.dump({
        'docker_image_name': 'web',
        'kube_service_name': 'web',
    }))
    return tmp_path


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    home = tmp_path / 'home'
    home.mkdir()
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setattr(pathlib.Path, 'home', classmethod(lambda cls: home))
    return home


def build_context(project_dir):
    return context_factories.InitialisedRepoContextFactory(project_dir).get()


class TestWorkspaceInContext:
    def test_inactive_by_default(self, project_dir, isolated_home, monkeypatch):
        monkeypatch.delenv('KUBEYARD_WORKSPACE', raising=False)

        context = build_context(project_dir)

        assert context['KUBEYARD_WORKSPACE'] == ''
        assert context['KUBEYARD_NAMESPACE'] == ''

    def test_marker_file_activates_workspace(self, project_dir, isolated_home, monkeypatch):
        monkeypatch.delenv('KUBEYARD_WORKSPACE', raising=False)
        (project_dir / '.kubeyard-workspace').write_text('example\n')

        context = build_context(project_dir)

        assert context['KUBEYARD_WORKSPACE'] == 'example'
        assert context['KUBEYARD_NAMESPACE'] == 'ws-example'

    def test_environment_variable_wins(self, project_dir, isolated_home, monkeypatch):
        (project_dir / '.kubeyard-workspace').write_text('from-marker\n')
        monkeypatch.setenv('KUBEYARD_WORKSPACE', 'from-env')

        context = build_context(project_dir)

        assert context['KUBEYARD_WORKSPACE'] == 'from-env'
        assert context['KUBEYARD_NAMESPACE'] == 'ws-from-env'

    def test_existing_keys_are_untouched_when_inactive(self, project_dir, isolated_home, monkeypatch):
        monkeypatch.delenv('KUBEYARD_WORKSPACE', raising=False)

        context = build_context(project_dir)

        assert context['DASHED_PROJECT_NAME'] == project_dir.name.replace('_', '-')
        assert context['KUBE_SERVICE_NAME'] == 'web'
        assert context['KUBEYARD_MODE'] == 'production'

    def test_workspace_is_exported_to_environment(self, project_dir, isolated_home, monkeypatch):
        monkeypatch.delenv('KUBEYARD_WORKSPACE', raising=False)
        (project_dir / '.kubeyard-workspace').write_text('example\n')

        environment = dict(build_context(project_dir).as_environment())

        assert environment['KUBEYARD_NAMESPACE'] == 'ws-example'

    def test_empty_marker_file_results_in_inactive_workspace(self, project_dir, isolated_home, monkeypatch):
        monkeypatch.delenv('KUBEYARD_WORKSPACE', raising=False)
        (project_dir / '.kubeyard-workspace').write_text('   \n')

        context = build_context(project_dir)

        assert context['KUBEYARD_WORKSPACE'] == ''
        assert context['KUBEYARD_NAMESPACE'] == ''


def test_project_dev_tld_survives_the_global_layer(project_dir, isolated_home, monkeypatch):
    """The global context is applied after the project one, so a default there would override it."""
    monkeypatch.delenv('KUBEYARD_WORKSPACE', raising=False)
    (project_dir / 'config' / 'kubeyard.yml').write_text(yaml.dump({
        'docker_image_name': 'web',
        'kube_service_name': 'web',
        'dev_tld': 'example.test',
    }))

    context = build_context(project_dir)

    assert context['DEV_TLD'] == 'example.test'
