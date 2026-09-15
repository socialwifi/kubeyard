"""
The invariant: with no marker file and no KUBEYARD_WORKSPACE, kubeyard behaves
exactly as it did before workspaces existed - in particular it emits no
--namespace flag anywhere.
"""
from kubeyard import aliases
from kubeyard import kubectl
from kubeyard import node_ports
from kubeyard import workspace


class TestInactiveWorkspaceEmitsNoNamespace:
    def test_namespace_args_is_empty(self):
        assert kubectl.namespace_args('') == ()

    def test_resolve_is_inactive_without_marker_or_env(self, tmp_path):
        assert workspace.resolve(tmp_path, {}) == workspace.INACTIVE

    def test_inactive_namespace_is_empty_string_not_default(self, tmp_path):
        resolved = workspace.resolve(tmp_path, {})

        assert resolved.namespace == ''
        assert resolved.namespace != workspace.DEFAULT_NAMESPACE


class TestSkipPredicateIsInertWithoutWorkspace:
    def test_no_definition_is_skipped_when_nothing_is_allocated(self):
        definition = {
            'kind': 'Service',
            'metadata': {'name': 'frontend-livereload-development'},
            'spec': {'ports': [{'port': 80, 'nodePort': 30555}]},
        }

        assert node_ports.should_skip(definition, {}, '') is False


class TestReconcileNeverDeletesRealServices:
    def test_to_delete_is_always_a_subset_of_existing_aliases(self):
        result = aliases.reconcile(
            shared_services={'web', 'api'},
            real_services={'web', 'frontend-development'},
            existing_aliases={'api'})

        assert set(result.to_delete).issubset({'api'})
