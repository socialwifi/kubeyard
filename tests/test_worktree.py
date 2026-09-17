from unittest import mock

import pytest

from kubeyard import settings
from kubeyard import worktree


class TestResolveRoot:
    def test_defaults_to_dot_worktrees(self):
        assert worktree.resolve_root(None, {}) == settings.DEFAULT_KUBEYARD_WORKTREE_ROOT == '.worktrees'

    def test_global_config_overrides_the_default(self):
        assert worktree.resolve_root(None, {'KUBEYARD_WORKTREE_ROOT': 'trees'}) == 'trees'

    def test_explicit_argument_wins_over_global_config(self):
        assert worktree.resolve_root('flag', {'KUBEYARD_WORKTREE_ROOT': 'config'}) == 'flag'

    def test_empty_config_value_falls_back_to_the_default(self):
        assert worktree.resolve_root(None, {'KUBEYARD_WORKTREE_ROOT': ''}) == '.worktrees'


class TestPathFor:
    def test_is_relative_to_the_project(self, tmp_path):
        assert worktree.path_for(tmp_path, '.worktrees', 'alice') == tmp_path / '.worktrees' / 'alice'

    def test_a_custom_root_stays_inside_the_project(self, tmp_path):
        """Repo-relative by construction, so the $HOME requirement cannot be escaped."""
        assert worktree.path_for(tmp_path, 'trees/nested', 'alice') == tmp_path / 'trees' / 'nested' / 'alice'

    def test_an_absolute_root_is_refused(self, tmp_path):
        with pytest.raises(worktree.InvalidWorktreeRoot):
            worktree.path_for(tmp_path, '/somewhere/else', 'alice')

    def test_a_root_escaping_the_project_is_refused(self, tmp_path):
        with pytest.raises(worktree.InvalidWorktreeRoot):
            worktree.path_for(tmp_path, '../outside', 'alice')


class TestBranchFor:
    def test_prefixes_the_workspace_name(self):
        assert worktree.branch_for('alice') == 'ws-alice'


class TestIsMainCheckout:
    def _git(self, git_dir, common_dir):
        def fake(*args, **kwargs):
            return git_dir if args[-1] == '--git-dir' else common_dir
        return fake

    def test_main_checkout_when_both_resolve_the_same(self, tmp_path):
        with mock.patch.object(worktree.sh, 'git', side_effect=self._git('.git', '.git')):
            assert worktree.is_main_checkout(tmp_path)

    def test_linked_worktree_when_they_differ(self, tmp_path):
        with mock.patch.object(
                worktree.sh, 'git',
                side_effect=self._git('/repo/.git/worktrees/alice', '/repo/.git')):
            assert not worktree.is_main_checkout(tmp_path)

    def test_relative_and_absolute_forms_of_the_same_directory_compare_equal(self, tmp_path):
        """git reports --git-dir relative to the project and --git-common-dir absolute."""
        (tmp_path / '.git').mkdir()
        with mock.patch.object(
                worktree.sh, 'git',
                side_effect=self._git('.git', str(tmp_path / '.git'))):
            assert worktree.is_main_checkout(tmp_path)


class TestEnsure:
    def test_creates_the_worktree_and_the_branch_when_neither_exists(self, tmp_path):
        path = tmp_path / '.worktrees' / 'alice'

        with mock.patch.object(worktree, 'branch_exists', return_value=False):
            with mock.patch.object(worktree.sh, 'git') as git:
                created = worktree.ensure(tmp_path, path, 'ws-alice')

        assert created
        assert git.call_args.args == (
            '-C', str(tmp_path), 'worktree', 'add', str(path), '-b', 'ws-alice')

    def test_reuses_an_existing_branch_rather_than_recreating_it(self, tmp_path):
        path = tmp_path / '.worktrees' / 'alice'

        with mock.patch.object(worktree, 'branch_exists', return_value=True):
            with mock.patch.object(worktree.sh, 'git') as git:
                worktree.ensure(tmp_path, path, 'ws-alice')

        assert git.call_args.args == ('-C', str(tmp_path), 'worktree', 'add', str(path), 'ws-alice')

    def test_an_existing_worktree_is_left_alone(self, tmp_path):
        path = tmp_path / '.worktrees' / 'alice'
        path.mkdir(parents=True)

        with mock.patch.object(worktree.sh, 'git') as git:
            created = worktree.ensure(tmp_path, path, 'ws-alice')

        assert not created
        git.assert_not_called()


class TestNameFromBranch:
    """
    create makes branch ws-<name>, so the branch fallback has to undo that or a
    second bare `workspace create` in the worktree yields ws-ws-<name>.
    """

    def test_strips_the_prefix_create_added(self):
        assert worktree.name_from_branch('ws-alice') == 'alice'

    def test_leaves_an_ordinary_branch_alone(self):
        assert worktree.name_from_branch('alice') == 'alice'

    def test_strips_only_the_leading_occurrence(self):
        assert worktree.name_from_branch('ws-ws-alice') == 'ws-alice'

    def test_a_branch_that_is_only_the_prefix_is_left_alone(self):
        assert worktree.name_from_branch('ws-') == 'ws-'

    def test_no_branch_stays_empty(self):
        assert worktree.name_from_branch('') == ''
