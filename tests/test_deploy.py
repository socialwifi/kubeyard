from unittest import mock

import sh

from kubepy import definition_manager

from kubeyard import dependencies
from kubeyard.commands import deploy
from kubeyard.commands import dev_requirements


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


class TestDefinitionDirectoriesHelper:
    """
    The module-level helper shared by DeployCommand.definition_directories and
    UndeployCommand.definition_directories - see also
    tests/test_undeploy.py::TestDefinitionDirectories, which pins the
    undeploy side (include_dev_overrides=True unconditionally).
    """

    def test_both_included_when_present_and_requested(self, tmp_path):
        kubernetes_dir = tmp_path / 'config' / 'kubernetes' / 'deploy'
        overrides_dir = tmp_path / 'config' / 'kubernetes' / 'development_overrides'
        kubernetes_dir.mkdir(parents=True)
        overrides_dir.mkdir(parents=True)

        result = deploy.definition_directories(tmp_path, include_dev_overrides=True)

        assert result == [kubernetes_dir, overrides_dir]

    def test_overrides_excluded_when_not_requested_even_if_present(self, tmp_path):
        kubernetes_dir = tmp_path / 'config' / 'kubernetes' / 'deploy'
        overrides_dir = tmp_path / 'config' / 'kubernetes' / 'development_overrides'
        kubernetes_dir.mkdir(parents=True)
        overrides_dir.mkdir(parents=True)

        result = deploy.definition_directories(tmp_path, include_dev_overrides=False)

        assert result == [kubernetes_dir]

    def test_missing_directories_are_never_included_regardless_of_the_flag(self, tmp_path):
        assert deploy.definition_directories(tmp_path, include_dev_overrides=True) == []
        assert deploy.definition_directories(tmp_path, include_dev_overrides=False) == []


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


class TestDevRequirementsDoNotInheritAnAlias:
    """
    The seam between deploy and dev_requirements, which each module passes on
    its own: the Service of a development requirement is created by
    "kubectl expose", never by a committed definition, so
    remove_shadowed_aliases cannot see it. If the alias survives, expose
    collides with it, the workspace keeps a Postgres pod with no Service of
    its own, and "dev-postgres" inside the workspace resolves to the shared
    database - so migrations and seeds run against it while the deploy
    reports success.
    """

    def _kubectl_side_effect(self, started_log):
        def side_effect(*args, **kwargs):
            if args[0] == 'logs':
                return [started_log]
            return ''
        return side_effect

    def test_the_alias_is_deleted_before_the_service_is_exposed(self):
        command = FakeDeployCommand(
            dict(context(namespace='ws-example', dev_requirements=[{'kind': 'postgres'}]),
                 KUBE_SERVICE_NAME='example'))
        started_log = dev_requirements.PostgresDependency.started_log

        with mock.patch.object(deploy.aliases, 'list_shared_services', return_value={'dev-postgres'}), \
                mock.patch.object(deploy.aliases, 'list_aliases', return_value={'dev-postgres'}), \
                mock.patch.object(dev_requirements.PostgresDependency, 'is_container_running',
                                  side_effect=[False, True]), \
                mock.patch.object(dependencies.aliases, 'delete') as alias_delete, \
                mock.patch.object(dependencies.sh, 'kubectl',
                                  side_effect=self._kubectl_side_effect(started_log)) as kubectl:
            manager = mock.Mock()
            manager.attach_mock(alias_delete, 'alias_delete')
            manager.attach_mock(kubectl, 'kubectl')
            command.run_dev_requirements_deploy()

        verbs = [call.args[0] for call in kubectl.call_args_list]
        assert 'expose' in verbs  # the requirement really did get as far as creating its Service
        alias_delete.assert_any_call('ws-example', ['dev-postgres'])
        names = [call[0] for call in manager.mock_calls]
        expose_index = next(
            index for index, call in enumerate(manager.mock_calls)
            if call[0] == 'kubectl' and call.args[0] == 'expose')
        assert names.index('alias_delete') < expose_index

    def test_no_alias_work_is_attempted_outside_a_workspace(self):
        command = FakeDeployCommand(
            dict(context(dev_requirements=[{'kind': 'postgres'}]), KUBE_SERVICE_NAME='example'))
        started_log = dev_requirements.PostgresDependency.started_log

        with mock.patch.object(dev_requirements.PostgresDependency, 'is_container_running',
                               side_effect=[False, True]), \
                mock.patch.object(dependencies.aliases, 'delete') as alias_delete, \
                mock.patch.object(dependencies.sh, 'kubectl',
                                  side_effect=self._kubectl_side_effect(started_log)):
            command.run_dev_requirements_deploy()

        alias_delete.assert_not_called()

    def test_an_existing_service_inside_a_workspace_is_reported_at_warning(self, caplog):
        # The collision used to be swallowed at DEBUG, which is what made the
        # whole failure invisible.
        dependency = dev_requirements.PostgresDependency('ws-example')
        already_exists = sh.ErrorReturnCode_1('kubectl', b'', b'services "dev-postgres" already exists')

        def side_effect(*args, **kwargs):
            if args[0] == 'expose':
                raise already_exists
            return ''

        with mock.patch.object(dependencies.aliases, 'delete'):
            with mock.patch.object(dependencies.sh, 'kubectl', side_effect=side_effect):
                with caplog.at_level('WARNING'):
                    dependency._apply_definition()

        assert any('dev-postgres' in record.message for record in caplog.records)


class TestRunDefaultSeeding:
    def make_command(self, tmp_path, **context_kwargs):
        deploy_dir = tmp_path / 'deploy'
        deploy_dir.mkdir()
        (deploy_dir / '01_deployment.yml').write_text('kind: Deployment\nmetadata:\n  name: web\n')
        return FakeDeployCommand(context(**context_kwargs), definition_directories=[deploy_dir])

    def test_seeds_when_the_database_is_freshly_created(self, tmp_path):
        command = self.make_command(
            tmp_path, seed_command='python -m tests.demo', dev_requirements=[{'kind': 'postgres'}])

        with mock.patch.object(deploy.DeployCommand, 'run_dev_requirements_deploy', return_value=True), \
                mock.patch.object(deploy.DeployCommand, 'run_kubernetes_deploy'), \
                mock.patch.object(deploy.DomainConfigurator, 'configure'), \
                mock.patch('kubeyard.commands.seed.SeedRunner') as seed_runner_cls:
            command.run_default()

        seed_runner_cls.assert_called_once_with(command.context)
        seed_runner_cls.return_value.wait_and_seed.assert_called_once_with(['web'])

    def test_does_not_seed_when_database_already_existed(self, tmp_path):
        command = self.make_command(
            tmp_path, seed_command='python -m tests.demo', dev_requirements=[{'kind': 'postgres'}])

        with mock.patch.object(deploy.DeployCommand, 'run_dev_requirements_deploy', return_value=False), \
                mock.patch.object(deploy.DeployCommand, 'run_kubernetes_deploy'), \
                mock.patch.object(deploy.DomainConfigurator, 'configure'), \
                mock.patch('kubeyard.commands.seed.SeedRunner') as seed_runner_cls:
            command.run_default()

        seed_runner_cls.assert_not_called()

    def test_does_not_seed_when_no_seed_command_configured(self, tmp_path):
        command = self.make_command(tmp_path, dev_requirements=[{'kind': 'postgres'}])

        with mock.patch.object(deploy.DeployCommand, 'run_dev_requirements_deploy', return_value=True), \
                mock.patch.object(deploy.DeployCommand, 'run_kubernetes_deploy'), \
                mock.patch.object(deploy.DomainConfigurator, 'configure'), \
                mock.patch('kubeyard.commands.seed.SeedRunner') as seed_runner_cls:
            command.run_default()

        seed_runner_cls.assert_not_called()

    def test_seeds_outside_a_workspace_too_when_the_database_is_new(self, tmp_path):
        """
        database_created means createdb just succeeded, so the database is empty
        wherever it is. Seeding an empty shared database only fills it in; a
        redeploy finds the database present and does not seed again.
        """
        command = self.make_command(
            tmp_path, namespace='', seed_command='python -m tests.demo',
            dev_requirements=[{'kind': 'postgres'}])

        with mock.patch.object(deploy.DeployCommand, 'run_dev_requirements_deploy', return_value=True), \
                mock.patch.object(deploy.DeployCommand, 'run_kubernetes_deploy'), \
                mock.patch.object(deploy.DomainConfigurator, 'configure'), \
                mock.patch('kubeyard.commands.seed.SeedRunner') as seed_runner_cls:
            command.run_default()

        seed_runner_cls.assert_called_once_with(command.context)

    def test_should_seed_requires_a_fresh_database_and_a_command(self):
        def command(**kwargs):
            return FakeDeployCommand(context(**kwargs))

        seed = 'python -m tests.demo'
        for namespace in ('ws-example', ''):
            assert command(namespace=namespace, seed_command=seed).should_seed(database_created=True)
            assert not command(namespace=namespace, seed_command=seed).should_seed(database_created=False)
            assert not command(namespace=namespace).should_seed(database_created=True)

    def test_does_not_run_dev_requirements_deploy_without_dev_requirements(self, tmp_path):
        command = self.make_command(tmp_path, seed_command='python -m tests.demo')

        with mock.patch.object(deploy.DeployCommand, 'run_dev_requirements_deploy') as run_dev_requirements, \
                mock.patch.object(deploy.DeployCommand, 'run_kubernetes_deploy'), \
                mock.patch.object(deploy.DomainConfigurator, 'configure'), \
                mock.patch('kubeyard.commands.seed.SeedRunner') as seed_runner_cls:
            command.run_default()

        run_dev_requirements.assert_not_called()
        seed_runner_cls.assert_not_called()
