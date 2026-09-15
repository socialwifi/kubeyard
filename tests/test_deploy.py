from unittest import mock

from kubepy import definition_manager

from kubeyard.commands import deploy


class FakeDeployCommand(deploy.DeployCommand):
    """
    Bypasses BaseDevelCommand.__init__, which would start minikube.
    """

    def __init__(self, context, *, definition_directories=(), build_url=None):
        self._context = context
        self._definition_directories = list(definition_directories)
        self.build_url = build_url

    @property
    def context(self):
        return self._context

    @property
    def definition_directories(self):
        return self._definition_directories

    @property
    def is_development(self):
        return self._context.get('KUBEYARD_MODE', 'development') == 'development'

    @property
    def dev_requirements(self):
        return self._context.get('DEV_REQUIREMENTS')

    @property
    def tag(self):
        return 'dev'

    @property
    def host_volumes(self):
        return {}


def context(namespace='', seed_command=None, dev_requirements=None):
    ctx = {'KUBEYARD_NAMESPACE': namespace, 'KUBEYARD_MODE': 'development'}
    if seed_command is not None:
        ctx['DEV_SEED_COMMAND'] = seed_command
    if dev_requirements is not None:
        ctx['DEV_REQUIREMENTS'] = dev_requirements
    return ctx


class TestOwnedNames:
    def test_extracts_kind_and_name_pairs(self, tmp_path):
        deploy_dir = tmp_path / 'config' / 'kubernetes' / 'deploy'
        deploy_dir.mkdir(parents=True)
        (deploy_dir / '01_deployment.yml').write_text(
            'apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: web\n')
        (deploy_dir / '02_service.yml').write_text(
            'apiVersion: v1\nkind: Service\nmetadata:\n  name: api\n')

        owned = deploy.owned_objects([deploy_dir])

        assert owned == [('Deployment', 'web'), ('Service', 'api')]

    def test_service_names_only(self, tmp_path):
        deploy_dir = tmp_path / 'deploy'
        deploy_dir.mkdir()
        (deploy_dir / '01_service.yml').write_text(
            'kind: Service\nmetadata:\n  name: api\n')
        (deploy_dir / '02_deployment.yml').write_text(
            'kind: Deployment\nmetadata:\n  name: web\n')

        assert deploy.owned_service_names([deploy_dir]) == ['api']

    def test_ignores_files_without_kind_or_name(self, tmp_path):
        deploy_dir = tmp_path / 'deploy'
        deploy_dir.mkdir()
        (deploy_dir / '01_fragment.yml').write_text('spec:\n  replicas: 1\n')

        assert deploy.owned_objects([deploy_dir]) == []

    def test_a_fragment_override_merges_into_the_base_definition(self, tmp_path):
        """
        Development overrides are normally fragments carrying only the keys
        they change, with kind and metadata.name left in the base file. kubepy
        deep-merges them at apply time, so anything deriving the deployed
        object list has to merge them too, or the object is deployed and then
        never undeployed.
        """
        base = tmp_path / 'deploy'
        overrides = tmp_path / 'development_overrides'
        base.mkdir()
        overrides.mkdir()
        (base / '01_deployment.yml').write_text(
            'apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: web\nspec:\n  replicas: 3\n')
        (overrides / '01_deployment.yml').write_text('spec:\n  replicas: 1\n')

        assert deploy.owned_objects([base, overrides]) == [('Deployment', 'web')]

    def test_merging_matches_kubepy_so_deploy_and_undeploy_agree(self, tmp_path):
        """
        The invariant behind the merge: whatever kubepy applies from these
        directories is what owned_objects must report.
        """
        base = tmp_path / 'deploy'
        overrides = tmp_path / 'development_overrides'
        base.mkdir()
        overrides.mkdir()
        (base / '01_deployment.yml').write_text(
            'apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: web\nspec:\n  replicas: 3\n')
        (base / '02_service.yml').write_text('kind: Service\nmetadata:\n  name: api\n')
        (overrides / '01_deployment.yml').write_text('spec:\n  replicas: 1\n')

        applied = definition_manager.OverridenDefinitionManager(
            definition_manager.DefinitionManager(base),
            definition_manager.DefinitionManager(overrides),
        )
        expected = [(d['kind'], d['metadata']['name']) for d in (applied[name] for name in applied)]

        assert deploy.owned_objects([base, overrides]) == expected

    def test_later_directories_override_earlier_ones_by_filename(self, tmp_path):
        base = tmp_path / 'deploy'
        overrides = tmp_path / 'development_overrides'
        base.mkdir()
        overrides.mkdir()
        (base / '01_service.yml').write_text('kind: Service\nmetadata:\n  name: frontend\n')
        (overrides / '01_service.yml').write_text(
            'kind: Service\nmetadata:\n  name: frontend-development\n')

        assert deploy.owned_service_names([base, overrides]) == ['frontend-development']


class TestNamespace:
    def test_defaults_to_empty_string(self):
        assert FakeDeployCommand({}).namespace == ''

    def test_reads_from_context(self):
        assert FakeDeployCommand(context(namespace='ws-example')).namespace == 'ws-example'


class TestDeploymentNames:
    def test_extracts_deployment_names_only(self, tmp_path):
        deploy_dir = tmp_path / 'deploy'
        deploy_dir.mkdir()
        (deploy_dir / '01_deployment.yml').write_text('kind: Deployment\nmetadata:\n  name: web\n')
        (deploy_dir / '02_service.yml').write_text('kind: Service\nmetadata:\n  name: api\n')
        command = FakeDeployCommand(context(), definition_directories=[deploy_dir])

        assert command.deployment_names == ['web']


class TestRunKubernetesDeploy:
    def test_without_workspace_matches_pre_workspace_behaviour(self):
        # Backward-compatibility pin: with no workspace active, Options gets
        # namespace=None, apply_all gets skip=None, no alias work happens and
        # the expensive allocated-nodePort kubectl lookup is never made.
        command = FakeDeployCommand(context(namespace=''), definition_directories=[])
        applier = mock.Mock()

        with mock.patch.object(deploy.kubepy.appliers, 'DirectoriesApplier', return_value=applier) as applier_cls, \
                mock.patch.object(deploy.kubernetes, 'install_secrets') as install_secrets, \
                mock.patch.object(deploy.aliases, 'delete') as alias_delete, \
                mock.patch.object(deploy.node_ports, 'allocated_node_ports') as allocated:
            command.run_kubernetes_deploy()

        options = applier_cls.call_args.args[1]
        assert not options.namespace
        applier.apply_all.assert_called_once_with(skip=None)
        applier.definitions_to_skip.assert_not_called()
        alias_delete.assert_not_called()
        allocated.assert_not_called()
        install_secrets.assert_called_once_with(command.context)

    def test_with_workspace_applies_into_namespace_and_removes_shadowed_aliases(self, tmp_path):
        deploy_dir = tmp_path / 'deploy'
        deploy_dir.mkdir()
        (deploy_dir / '01_service.yml').write_text('kind: Service\nmetadata:\n  name: api\n')
        command = FakeDeployCommand(context(namespace='ws-example'), definition_directories=[deploy_dir])
        applier = mock.Mock()
        applier.definitions_to_skip.return_value = []

        with mock.patch.object(deploy.kubepy.appliers, 'DirectoriesApplier', return_value=applier) as applier_cls, \
                mock.patch.object(deploy.kubernetes, 'install_secrets'), \
                mock.patch.object(deploy.aliases, 'delete') as alias_delete, \
                mock.patch.object(deploy.node_ports, 'allocated_node_ports', return_value={}):
            manager = mock.Mock()
            manager.attach_mock(alias_delete, 'alias_delete')
            manager.attach_mock(applier.apply_all, 'apply_all')
            command.run_kubernetes_deploy()

        options = applier_cls.call_args.args[1]
        assert options.namespace == 'ws-example'
        applier.apply_all.assert_called_once_with(skip=command.skip_predicate)
        alias_delete.assert_called_once_with('ws-example', ['api'])
        # Design point 5: the alias must be removed *before* apply_all runs, so
        # a real Service replaces it rather than colliding with the leftover
        # ExternalName of the same name.
        assert manager.mock_calls == [
            mock.call.alias_delete('ws-example', ['api']),
            mock.call.apply_all(skip=command.skip_predicate),
        ]


class TestReportSkipped:
    def test_no_predicate_reports_nothing(self):
        command = FakeDeployCommand(context(namespace=''))
        applier = mock.Mock()

        with mock.patch.object(deploy.logger, 'warning') as warning:
            command.report_skipped(applier)

        warning.assert_not_called()
        applier.definitions_to_skip.assert_not_called()

    def test_warns_with_reason_for_each_skipped_definition(self):
        command = FakeDeployCommand(context(namespace='ws-example'))
        definition = {
            'kind': 'Service', 'metadata': {'name': 'frontend-livereload'},
            'spec': {'ports': [{'port': 80, 'nodePort': 30555}]},
        }
        applier = mock.Mock()
        applier.definitions_to_skip.return_value = [definition]

        with mock.patch.object(
                deploy.node_ports, 'allocated_node_ports',
                return_value={30555: 'default/frontend-livereload'}):
            with mock.patch.object(deploy.logger, 'warning') as warning:
                command.report_skipped(applier)

        applier.definitions_to_skip.assert_called_once_with(command.skip_predicate)
        warning.assert_called_once()
        assert 'frontend-livereload' in warning.call_args.args[0]


class TestRemoveShadowedAliases:
    def test_no_owned_services_does_not_call_delete(self, tmp_path):
        deploy_dir = tmp_path / 'deploy'
        deploy_dir.mkdir()
        (deploy_dir / '01_deployment.yml').write_text('kind: Deployment\nmetadata:\n  name: web\n')
        command = FakeDeployCommand(context(namespace='ws-example'), definition_directories=[deploy_dir])

        with mock.patch.object(deploy.aliases, 'delete') as alias_delete:
            command.remove_shadowed_aliases()

        alias_delete.assert_not_called()

    def test_owned_services_are_removed(self, tmp_path):
        deploy_dir = tmp_path / 'deploy'
        deploy_dir.mkdir()
        (deploy_dir / '01_service.yml').write_text('kind: Service\nmetadata:\n  name: api\n')
        command = FakeDeployCommand(context(namespace='ws-example'), definition_directories=[deploy_dir])

        with mock.patch.object(deploy.aliases, 'delete') as alias_delete:
            command.remove_shadowed_aliases()

        alias_delete.assert_called_once_with('ws-example', ['api'])

    def test_a_service_that_will_be_skipped_keeps_its_alias(self, tmp_path):
        """Found in a real workspace: the alias went, the Service was then skipped, and the name
        resolved to nothing - the exact state the overlay exists to prevent."""
        deploy_dir = tmp_path / 'deploy'
        deploy_dir.mkdir()
        (deploy_dir / '01_service.yml').write_text('kind: Service\nmetadata:\n  name: api\n')
        (deploy_dir / '02_livereload.yml').write_text(
            'kind: Service\nmetadata:\n  name: livereload\n'
            'spec:\n  type: NodePort\n  ports:\n    - nodePort: 30555\n')
        command = FakeDeployCommand(context(namespace='ws-example'), definition_directories=[deploy_dir])

        with mock.patch.object(deploy.node_ports, 'allocated_node_ports',
                               return_value={30555: 'default/livereload'}):
            with mock.patch.object(deploy.aliases, 'delete') as alias_delete:
                command.remove_shadowed_aliases()

        alias_delete.assert_called_once_with('ws-example', ['api'])

    def test_a_service_holding_its_own_port_still_loses_its_alias(self, tmp_path):
        """The port is this workspace's own, so the Service is applied and really does shadow."""
        deploy_dir = tmp_path / 'deploy'
        deploy_dir.mkdir()
        (deploy_dir / '01_livereload.yml').write_text(
            'kind: Service\nmetadata:\n  name: livereload\n'
            'spec:\n  type: NodePort\n  ports:\n    - nodePort: 30555\n')
        command = FakeDeployCommand(context(namespace='ws-example'), definition_directories=[deploy_dir])

        with mock.patch.object(deploy.node_ports, 'allocated_node_ports',
                               return_value={30555: 'ws-example/livereload'}):
            with mock.patch.object(deploy.aliases, 'delete') as alias_delete:
                command.remove_shadowed_aliases()

        alias_delete.assert_called_once_with('ws-example', ['livereload'])


class TestSkipPredicate:
    def test_none_without_workspace(self):
        command = FakeDeployCommand(context(namespace=''))

        assert command.skip_predicate is None

    def test_built_from_allocated_ports_with_workspace(self):
        command = FakeDeployCommand(context(namespace='ws-example'))
        definition = {
            'kind': 'Service', 'metadata': {'name': 'x'},
            'spec': {'ports': [{'port': 80, 'nodePort': 30555}]},
        }

        with mock.patch.object(
                deploy.node_ports, 'allocated_node_ports', return_value={30555: 'default/other'}):
            predicate = command.skip_predicate

        assert predicate(definition) is True

    def test_allocated_node_ports_is_looked_up_only_once(self):
        # cached_property must prevent a second kubectl shell-out.
        command = FakeDeployCommand(context(namespace='ws-example'))

        with mock.patch.object(deploy.node_ports, 'allocated_node_ports', return_value={}) as allocated:
            command._allocated_node_ports
            command._allocated_node_ports
            command.skip_predicate

        allocated.assert_called_once()


class TestRunDevRequirementsDeploy:
    def test_returns_true_when_dispatcher_created_a_database(self):
        command = FakeDeployCommand(context())

        with mock.patch('kubeyard.commands.dev_requirements.RequirementsDispatcher') as dispatcher_cls:
            dispatcher_cls.return_value.dispatch_all.return_value = True
            result = command.run_dev_requirements_deploy()

        assert result is True

    def test_returns_false_when_dispatcher_created_nothing(self):
        command = FakeDeployCommand(context())

        with mock.patch('kubeyard.commands.dev_requirements.RequirementsDispatcher') as dispatcher_cls:
            dispatcher_cls.return_value.dispatch_all.return_value = False
            result = command.run_dev_requirements_deploy()

        assert result is False
