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


def test_project_domains_suffix_survives_the_global_layer(project_dir, isolated_home, monkeypatch):
    """The global context is applied after the project one, so a default there would override it."""
    monkeypatch.delenv('KUBEYARD_WORKSPACE', raising=False)
    (project_dir / 'config' / 'kubeyard.yml').write_text(yaml.dump({
        'docker_image_name': 'web',
        'kube_service_name': 'web',
        'dev_domains_suffix': 'example.test',
    }))

    context = build_context(project_dir)

    assert context['DEV_DOMAINS_SUFFIX'] == 'example.test'


def test_base_domain_in_a_project_is_rejected(project_dir, isolated_home, monkeypatch):
    """One ConfigMap serves every service in the namespace, so no project may name it."""
    monkeypatch.delenv('KUBEYARD_WORKSPACE', raising=False)
    (project_dir / 'config' / 'kubeyard.yml').write_text(yaml.dump({
        'docker_image_name': 'web',
        'kube_service_name': 'web',
        'base_domain': 'example.test',
    }))

    with pytest.raises(context_factories.ConfigurationError, match='base_domain'):
        build_context(project_dir)


def test_project_scoped_key_in_the_user_file_is_rejected(project_dir, isolated_home, monkeypatch):
    """It would apply to every project, and no project could ask for a different value."""
    monkeypatch.delenv('KUBEYARD_WORKSPACE', raising=False)
    (project_dir / 'config' / 'kubeyard.yml').write_text(yaml.dump({
        'docker_image_name': 'web',
        'kube_service_name': 'web',
    }))
    user_context = isolated_home / '.kubeyard' / 'context.yml'
    user_context.parent.mkdir(parents=True, exist_ok=True)
    user_context.write_text(yaml.dump({'dev_domains_suffix': 'example.test'}))

    with pytest.raises(context_factories.ConfigurationError, match='dev_domains_suffix'):
        build_context(project_dir)


def test_renamed_key_says_what_it_became(project_dir, isolated_home, monkeypatch):
    monkeypatch.delenv('KUBEYARD_WORKSPACE', raising=False)
    (project_dir / 'config' / 'kubeyard.yml').write_text(yaml.dump({
        'docker_image_name': 'web',
        'kube_service_name': 'web',
        'dev_tld': 'example.test',
    }))

    with pytest.raises(context_factories.ConfigurationError, match='dev_domains_suffix'):
        build_context(project_dir)


class TestEnvironmentValue:
    def test_missing_option_is_empty_rather_than_the_string_null(self):
        assert dict(context_factories.Context({'BUILD_URL': None}).as_environment()) == {'BUILD_URL': ''}

    def test_flags_read_as_shell_expects(self):
        flags = context_factories.Context({'ON': True, 'OFF': False})
        assert dict(flags.as_environment()) == {'ON': 'true', 'OFF': 'false'}

    def test_numbers_lose_the_yaml_document_marker(self):
        assert dict(context_factories.Context({'PORT': 80}).as_environment()) == {'PORT': '80'}

    def test_lists_stay_yaml_because_they_have_no_plainer_form(self):
        listed = context_factories.Context({'DEV_DOMAINS': ['panel', 'api']})
        assert dict(listed.as_environment()) == {'DEV_DOMAINS': '- panel\n- api\n'}
