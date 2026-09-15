"""
The invariant: with no marker file and no KUBEYARD_WORKSPACE, kubeyard behaves
exactly as it did before workspaces existed - in particular it emits no
--namespace flag anywhere.
"""
from unittest import mock

from kubeyard import aliases
from kubeyard import kubectl
from kubeyard import node_ports
from kubeyard import workspace
from kubeyard.commands import deploy


class DeployCommandWithoutMinikube(deploy.DeployCommand):
    """
    Bypasses BaseDevelCommand.__init__, which would start minikube.

    Everything run() would reach is left as the real implementation, so this
    exercises DeployCommand.run_kubernetes_deploy itself rather than a stub.
    """

    def __init__(self, context):
        self._context = context
        self.build_url = None

    @property
    def context(self):
        return self._context

    @property
    def definition_directories(self):
        return []

    @property
    def is_development(self):
        return True

    @property
    def tag(self):
        return 'dev'

    @property
    def host_volumes(self):
        return {}


class TestInactiveWorkspaceEmitsNoNamespace:
    def test_namespace_args_is_empty(self):
        assert kubectl.namespace_args('') == ()

    def test_resolve_is_inactive_without_marker_or_env(self, tmp_path):
        assert workspace.resolve(tmp_path, {}) == workspace.INACTIVE

    def test_inactive_namespace_is_empty_string_not_default(self, tmp_path):
        resolved = workspace.resolve(tmp_path, {})

        assert resolved.namespace == ''
        assert resolved.namespace != workspace.DEFAULT_NAMESPACE


class TestDeployWithoutWorkspaceIsUnchangedEndToEnd:
    """
    The same invariant the unit tests pin one piece at a time, asserted once on
    a real deploy: with an empty context, kubeyard issues no kubectl call of
    its own and hands kubepy no namespace, so it applies into whatever the
    user's kubectl context selects - exactly as it did before workspaces.
    """

    def _run(self, context):
        command = DeployCommandWithoutMinikube(context)
        applier = mock.Mock()
        applier.definitions_to_skip.return_value = []

        with mock.patch.object(deploy.kubepy.appliers, 'DirectoriesApplier', return_value=applier) as applier_cls, \
                mock.patch.object(deploy.kubernetes, 'install_secrets'), \
                mock.patch.object(aliases.sh, 'kubectl') as alias_kubectl, \
                mock.patch.object(node_ports.sh, 'kubectl', return_value='') as node_ports_kubectl, \
                mock.patch.object(deploy.sh, 'kubectl') as deploy_kubectl:
            command.run_kubernetes_deploy()

        options = applier_cls.call_args.args[1]
        calls = alias_kubectl.call_args_list + node_ports_kubectl.call_args_list + deploy_kubectl.call_args_list
        return options, applier, calls

    def test_no_kubectl_call_is_made_and_no_namespace_is_passed_to_kubepy(self):
        options, applier, calls = self._run({'KUBEYARD_MODE': 'development'})

        assert calls == []
        assert options.namespace == ''
        applier.apply_all.assert_called_once_with(skip=None)

    def test_an_active_workspace_is_what_changes_both(self):
        # Proves the assertions above are about the empty context and not
        # merely about everything being mocked out.
        options, applier, calls = self._run(
            {'KUBEYARD_MODE': 'development', 'KUBEYARD_NAMESPACE': 'ws-example'})

        assert options.namespace == 'ws-example'
        assert applier.apply_all.call_args.kwargs['skip'] is not None
        assert calls  # the nodePort lookup kubeyard only makes inside a workspace


class TestSkipPredicateIsInertWithoutWorkspace:
    def test_no_definition_is_skipped_when_nothing_is_allocated(self):
        definition = {
            'kind': 'Service',
            'metadata': {'name': 'frontend-livereload-development'},
            'spec': {'ports': [{'port': 80, 'nodePort': 30555}]},
        }

        assert node_ports.should_skip(definition, {}, '') is False


class TestReconcileNeverDeletesRealServices:
    def test_only_an_existing_alias_is_ever_deleted(self):
        # to_delete must be non-empty for this to mean anything: with inputs
        # that reconcile to no deletions at all, "is a subset of the existing
        # aliases" holds for any implementation, including one that never
        # deletes anything.
        result = aliases.reconcile(
            shared_services=set(),
            real_services={'web', 'api', 'frontend-development'},
            existing_aliases={'api'})

        assert result.to_delete == ['api']
        assert 'web' not in result.to_delete
        assert 'frontend-development' not in result.to_delete
