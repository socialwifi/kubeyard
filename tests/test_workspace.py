import pytest

from kubeyard import workspace


class TestNormalizeName:
    def test_lowercases(self):
        assert workspace.normalize_name('FEATURE-1') == 'feature-1'

    def test_collapses_non_alphanumeric_runs_to_single_dash(self):
        assert workspace.normalize_name('feature/Some Thing_x') == 'feature-some-thing-x'

    def test_strips_leading_and_trailing_dashes(self):
        assert workspace.normalize_name('--feature-1--') == 'feature-1'

    def test_leaves_already_normal_names_untouched(self):
        assert workspace.normalize_name('example') == 'example'


class TestValidateName:
    def test_returns_normalized_name(self):
        assert workspace.validate_name('FEATURE_1') == 'feature-1'

    def test_rejects_empty(self):
        with pytest.raises(workspace.InvalidWorkspaceName):
            workspace.validate_name('')

    def test_rejects_name_that_normalizes_to_empty(self):
        with pytest.raises(workspace.InvalidWorkspaceName):
            workspace.validate_name('---')

    def test_rejects_name_longer_than_30_characters(self):
        with pytest.raises(workspace.InvalidWorkspaceName):
            workspace.validate_name('a' * 31)

    def test_accepts_name_of_exactly_30_characters(self):
        assert workspace.validate_name('a' * 30) == 'a' * 30

    def test_error_message_names_the_offending_value(self):
        with pytest.raises(workspace.InvalidWorkspaceName) as excinfo:
            workspace.validate_name('a' * 31)

        assert 'a' * 31 in str(excinfo.value)


class TestNamespaceFor:
    def test_prefixes_with_ws(self):
        assert workspace.namespace_for('example') == 'ws-example'


class TestMarkerFile:
    def test_missing_marker_reads_as_empty(self, tmp_path):
        assert workspace.read_marker(tmp_path) == ''

    def test_written_marker_round_trips(self, tmp_path):
        workspace.write_marker(tmp_path, 'example')

        assert workspace.read_marker(tmp_path) == 'example'

    def test_marker_is_read_stripped_of_whitespace(self, tmp_path):
        (tmp_path / workspace.MARKER_FILENAME).write_text('  example \n')

        assert workspace.read_marker(tmp_path) == 'example'

    def test_remove_marker_is_idempotent(self, tmp_path):
        workspace.remove_marker(tmp_path)
        workspace.write_marker(tmp_path, 'example')
        workspace.remove_marker(tmp_path)

        assert workspace.read_marker(tmp_path) == ''


class TestResolve:
    def test_no_marker_and_no_env_is_inactive(self, tmp_path):
        resolved = workspace.resolve(tmp_path, {})

        assert resolved.name == ''
        assert resolved.namespace == ''

    def test_marker_file_activates_workspace(self, tmp_path):
        workspace.write_marker(tmp_path, 'example')

        resolved = workspace.resolve(tmp_path, {})

        assert resolved.name == 'example'
        assert resolved.namespace == 'ws-example'

    def test_environment_variable_overrides_marker(self, tmp_path):
        workspace.write_marker(tmp_path, 'from-marker')

        resolved = workspace.resolve(tmp_path, {'KUBEYARD_WORKSPACE': 'from-env'})

        assert resolved.name == 'from-env'
        assert resolved.namespace == 'ws-from-env'

    def test_empty_environment_variable_forces_shared_environment(self, tmp_path):
        workspace.write_marker(tmp_path, 'from-marker')

        resolved = workspace.resolve(tmp_path, {'KUBEYARD_WORKSPACE': ''})

        assert resolved.name == ''
        assert resolved.namespace == ''

    def test_environment_variable_is_normalized(self, tmp_path):
        resolved = workspace.resolve(tmp_path, {'KUBEYARD_WORKSPACE': 'FEATURE_1'})

        assert resolved.name == 'feature-1'

    def test_invalid_name_raises(self, tmp_path):
        with pytest.raises(workspace.InvalidWorkspaceName):
            workspace.resolve(tmp_path, {'KUBEYARD_WORKSPACE': 'a' * 31})

    def test_accepts_string_project_dir(self, tmp_path):
        workspace.write_marker(tmp_path, 'example')

        assert workspace.resolve(str(tmp_path), {}).name == 'example'
