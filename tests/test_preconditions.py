import pathlib

from unittest import mock

import pytest

from kubeyard import preconditions


class TestDevelopmentMode:
    def test_passes_in_development(self):
        preconditions.check_development_mode({'KUBEYARD_MODE': 'development'})

    def test_raises_in_production(self):
        with pytest.raises(preconditions.PreconditionFailed) as excinfo:
            preconditions.check_development_mode({'KUBEYARD_MODE': 'production'})

        assert 'development' in str(excinfo.value)

    def test_raises_when_mode_missing(self):
        with pytest.raises(preconditions.PreconditionFailed):
            preconditions.check_development_mode({})


class TestKubectlContext:
    def test_passes_on_expected_context(self):
        preconditions.check_kubectl_context('minikube')

    def test_raises_on_unexpected_context(self):
        with pytest.raises(preconditions.PreconditionFailed) as excinfo:
            preconditions.check_kubectl_context('gke-production')

        assert 'gke-production' in str(excinfo.value)
        assert 'minikube' in str(excinfo.value)

    def test_accepts_configured_expected_context(self):
        preconditions.check_kubectl_context('other-dev', expected='other-dev')


class TestProjectDirUnderHome:
    def test_passes_inside_home(self):
        preconditions.check_project_dir_under_home(
            pathlib.Path('/home/dev/work/frontend'), pathlib.Path('/home/dev'))

    def test_raises_outside_home(self):
        with pytest.raises(preconditions.PreconditionFailed) as excinfo:
            preconditions.check_project_dir_under_home(
                pathlib.Path('/mnt/work/frontend'), pathlib.Path('/home/dev'))

        assert '/mnt/work/frontend' in str(excinfo.value)

    def test_home_itself_passes(self):
        preconditions.check_project_dir_under_home(pathlib.Path('/home/dev'), pathlib.Path('/home/dev'))


class TestCurrentKubectlContext:
    def test_invokes_kubectl_config_current_context(self):
        with mock.patch.object(preconditions.sh, 'kubectl', return_value='minikube\n') as kubectl:
            result = preconditions.current_kubectl_context()

        kubectl.assert_called_once_with('config', 'current-context')
        assert result == 'minikube'


class TestCheckAll:
    def test_raises_when_not_in_development_mode_without_touching_the_cluster(self):
        with mock.patch.object(preconditions.sh, 'kubectl') as kubectl:
            with pytest.raises(preconditions.PreconditionFailed):
                preconditions.check_all({'KUBEYARD_MODE': 'production'}, pathlib.Path('/home/dev/work/frontend'))

        kubectl.assert_not_called()

    def test_raises_when_kubectl_context_is_unexpected(self, tmp_path, monkeypatch):
        monkeypatch.setattr(pathlib.Path, 'home', lambda: tmp_path)
        project_dir = tmp_path / 'work' / 'frontend'
        project_dir.mkdir(parents=True)

        with mock.patch.object(preconditions.sh, 'kubectl', return_value='gke-production\n'):
            with pytest.raises(preconditions.PreconditionFailed):
                preconditions.check_all({'KUBEYARD_MODE': 'development'}, project_dir)

    def test_raises_when_project_dir_is_outside_home(self, tmp_path, monkeypatch):
        monkeypatch.setattr(pathlib.Path, 'home', lambda: tmp_path / 'home')
        (tmp_path / 'home').mkdir()
        outside_dir = tmp_path / 'elsewhere' / 'frontend'
        outside_dir.mkdir(parents=True)

        with mock.patch.object(preconditions.sh, 'kubectl', return_value='minikube\n'):
            with pytest.raises(preconditions.PreconditionFailed):
                preconditions.check_all({'KUBEYARD_MODE': 'development'}, outside_dir)

    def test_passes_when_every_precondition_is_met(self, tmp_path, monkeypatch):
        monkeypatch.setattr(pathlib.Path, 'home', lambda: tmp_path)
        project_dir = tmp_path / 'work' / 'frontend'
        project_dir.mkdir(parents=True)

        with mock.patch.object(preconditions.sh, 'kubectl', return_value='minikube\n'):
            preconditions.check_all({'KUBEYARD_MODE': 'development'}, project_dir)
