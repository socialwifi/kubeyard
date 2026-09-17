import json

from unittest import mock

import pytest

from kubeyard import aliases
from kubeyard import dependencies


class TestReconcile:
    def test_aliases_every_shared_service_in_an_empty_workspace(self):
        result = aliases.reconcile(
            shared_services={'accounts', 'billing'}, real_services=set(), existing_aliases=set())

        assert result.to_create == ['accounts', 'billing']
        assert result.to_delete == []

    def test_does_not_alias_a_service_deployed_for_real(self):
        result = aliases.reconcile(
            shared_services={'accounts', 'billing'},
            real_services={'accounts'},
            existing_aliases=set())

        assert result.to_create == ['billing']
        assert result.to_delete == []

    def test_deletes_alias_shadowed_by_a_real_service(self):
        result = aliases.reconcile(
            shared_services={'accounts'}, real_services={'accounts'}, existing_aliases={'accounts'})

        assert result.to_create == []
        assert result.to_delete == ['accounts']

    def test_deletes_alias_whose_shared_service_disappeared(self):
        result = aliases.reconcile(
            shared_services=set(), real_services=set(), existing_aliases={'retired'})

        assert result.to_create == []
        assert result.to_delete == ['retired']

    def test_adds_alias_for_newly_added_shared_service(self):
        result = aliases.reconcile(
            shared_services={'accounts', 'newcomer'},
            real_services=set(),
            existing_aliases={'accounts'})

        assert result.to_create == ['newcomer']
        assert result.to_delete == []

    def test_never_deletes_a_name_that_is_not_an_existing_alias(self):
        result = aliases.reconcile(
            shared_services={'accounts'},
            real_services={'accounts', 'frontend'},
            existing_aliases=set())

        assert result.to_delete == []

    def test_is_idempotent(self):
        first = aliases.reconcile(
            shared_services={'accounts', 'billing'},
            real_services={'accounts'},
            existing_aliases=set())
        second = aliases.reconcile(
            shared_services={'accounts', 'billing'},
            real_services={'accounts'},
            existing_aliases=set(first.to_create))

        assert second.to_create == []
        assert second.to_delete == []

    def test_to_delete_is_always_a_subset_of_existing_aliases(self):
        # A real Service is never a candidate for deletion, even if it shares a
        # name with something reconcile has never heard of as an alias.
        result = aliases.reconcile(
            shared_services=set(),
            real_services={'accounts', 'billing', 'frontend'},
            existing_aliases={'accounts'})

        assert set(result.to_delete) <= {'accounts'}
        assert result.to_delete == ['accounts']


class TestAliasDefinition:
    def test_points_at_the_default_namespace(self):
        definition = aliases.alias_definition('accounts', 'ws-example')

        assert definition['kind'] == 'Service'
        assert definition['metadata']['name'] == 'accounts'
        assert definition['metadata']['namespace'] == 'ws-example'
        assert definition['spec']['type'] == 'ExternalName'
        assert definition['spec']['externalName'] == 'accounts.default.svc.cluster.local'

    def test_carries_the_alias_label(self):
        definition = aliases.alias_definition('accounts', 'ws-example')

        assert definition['metadata']['labels'][aliases.ALIAS_LABEL] == 'true'


class TestDeleteOnlyTouchesAliases:
    def test_real_service_passed_by_mistake_is_not_deleted(self):
        with mock.patch.object(aliases, 'list_aliases', return_value={'billing'}):
            with mock.patch.object(aliases.sh, 'kubectl') as kubectl:
                aliases.delete('ws-example', ['billing', 'accounts'])

        deleted = [call[0][2] for call in kubectl.call_args_list]
        assert deleted == ['billing']

    def test_deletes_nothing_when_no_names_are_aliases(self):
        with mock.patch.object(aliases, 'list_aliases', return_value=set()):
            with mock.patch.object(aliases.sh, 'kubectl') as kubectl:
                aliases.delete('ws-example', ['accounts'])

        assert kubectl.call_args_list == []


class TestDeleteNamespaceThreading:
    def test_no_namespace_flag_when_workspace_inactive(self):
        with mock.patch.object(aliases, 'list_aliases', return_value={'accounts'}):
            with mock.patch.object(aliases.sh, 'kubectl') as kubectl:
                aliases.delete('', ['accounts'])

        assert '--namespace' not in kubectl.call_args[0]

    def test_namespace_flag_when_workspace_active(self):
        with mock.patch.object(aliases, 'list_aliases', return_value={'accounts'}):
            with mock.patch.object(aliases.sh, 'kubectl') as kubectl:
                aliases.delete('ws-example', ['accounts'])

        assert '--namespace' in kubectl.call_args[0]
        assert 'ws-example' in kubectl.call_args[0]


class TestListServicesNamespaceThreading:
    def test_no_namespace_flag_when_workspace_inactive(self):
        with mock.patch.object(aliases.sh, 'kubectl', return_value='') as kubectl:
            aliases.list_services('')

        assert '--namespace' not in kubectl.call_args[0]

    def test_namespace_flag_when_workspace_active(self):
        with mock.patch.object(aliases.sh, 'kubectl', return_value='') as kubectl:
            aliases.list_services('ws-example')

        assert '--namespace' in kubectl.call_args[0]
        assert 'ws-example' in kubectl.call_args[0]

    def test_parses_space_separated_names(self):
        with mock.patch.object(aliases.sh, 'kubectl', return_value='accounts billing\n'):
            result = aliases.list_services('ws-example')

        assert result == {'accounts', 'billing'}

    def test_empty_output_is_an_empty_set(self):
        with mock.patch.object(aliases.sh, 'kubectl', return_value=''):
            result = aliases.list_services('ws-example')

        assert result == set()

    def test_kubectl_error_is_never_reported_as_no_services(self):
        # "the call failed" and "there is nothing there" must stay
        # distinguishable: reconciliation reads an empty shared listing as
        # "every alias is retired" and deletes the lot.
        with mock.patch.object(aliases.sh, 'kubectl', side_effect=aliases.sh.ErrorReturnCode('kubectl', b'', b'')):
            with pytest.raises(aliases.ServiceListingFailed) as excinfo:
                aliases.list_services('ws-example')

        assert 'ws-example' in str(excinfo.value)

    def test_the_shared_listing_names_the_default_namespace_when_it_fails(self):
        with mock.patch.object(aliases.sh, 'kubectl', side_effect=aliases.sh.ErrorReturnCode('kubectl', b'', b'')):
            with pytest.raises(aliases.ServiceListingFailed) as excinfo:
                aliases.list_shared_services()

        assert 'default' in str(excinfo.value)


class TestListAliasesNamespaceThreading:
    def test_no_namespace_flag_when_workspace_inactive(self):
        with mock.patch.object(aliases.sh, 'kubectl', return_value='') as kubectl:
            aliases.list_aliases('')

        assert '--namespace' not in kubectl.call_args[0]

    def test_namespace_flag_when_workspace_active(self):
        with mock.patch.object(aliases.sh, 'kubectl', return_value='') as kubectl:
            aliases.list_aliases('ws-example')

        assert '--namespace' in kubectl.call_args[0]

    def test_uses_the_alias_label_selector(self):
        with mock.patch.object(aliases.sh, 'kubectl', return_value='') as kubectl:
            aliases.list_aliases('ws-example')

        assert '--selector' in kubectl.call_args[0]
        assert '{}=true'.format(aliases.ALIAS_LABEL) in kubectl.call_args[0]


class TestListSharedServices:
    def test_always_targets_the_default_namespace(self):
        with mock.patch.object(aliases.sh, 'kubectl', return_value='') as kubectl:
            aliases.list_shared_services()

        assert '--namespace' in kubectl.call_args[0]
        assert 'default' in kubectl.call_args[0]

    def test_offers_ordinary_shared_services(self):
        with mock.patch.object(aliases.sh, 'kubectl', return_value='accounts billing'):
            assert aliases.list_shared_services() == {'accounts', 'billing'}

    def test_never_offers_a_service_kubeyard_provisions_per_workspace(self):
        # The workspace runs its own dev-postgres and dev-rabbitmq; aliasing
        # those names would point migrations, seeds and workers at the shared
        # instances while the workspace's own pods sat there unused.
        with mock.patch.object(
                aliases.sh, 'kubectl', return_value='accounts dev-postgres dev-rabbitmq dev-redis'):
            assert aliases.list_shared_services() == {'accounts'}

    def test_never_offers_the_cluster_api_service(self):
        with mock.patch.object(aliases.sh, 'kubectl', return_value='accounts kubernetes'):
            assert aliases.list_shared_services() == {'accounts'}


class TestNeverAliasedServices:
    def test_covers_the_requirements_kubeyard_ships(self):
        assert {'dev-postgres', 'dev-rabbitmq', 'dev-redis'} <= aliases.never_aliased_services()

    def test_covers_the_cluster_api_service(self):
        assert aliases.KUBERNETES_API_SERVICE in aliases.never_aliased_services()

    def test_a_newly_registered_requirement_is_covered_without_editing_a_list(self):
        # The set is derived from the requirement registry, so it cannot drift
        # when a requirement is added. A hardcoded list would fail this.
        from kubeyard.commands import dev_requirements

        class LaterDependency(dependencies.KubernetesDependency):
            name = 'dev-later'

        class Later(dev_requirements.Requirement):
            dependency_class = LaterDependency

        registry = dict(dev_requirements.RequirementsDispatcher.commands, later=Later)
        with mock.patch.object(dev_requirements.RequirementsDispatcher, 'commands', registry):
            assert 'dev-later' in aliases.never_aliased_services()


class TestListRealServices:
    def test_subtracts_aliases_from_all_services(self):
        with mock.patch.object(aliases, 'list_services', return_value={'accounts', 'billing'}):
            with mock.patch.object(aliases, 'list_aliases', return_value={'billing'}):
                result = aliases.list_real_services('ws-example')

        assert result == {'accounts'}


class TestApply:
    def test_applies_a_definition_for_each_name_embedding_the_target_namespace(self):
        with mock.patch.object(aliases.sh, 'kubectl') as kubectl:
            with mock.patch.object(aliases.sh, 'echo') as echo:
                aliases.apply('ws-example', ['accounts', 'billing'])

        assert kubectl.call_count == 2
        for call in kubectl.call_args_list:
            assert call[0][1:] == ('apply', '--namespace', 'ws-example', '-f', '-')

        payloads = [json.loads(call[0][0]) for call in echo.call_args_list]
        assert {payload['metadata']['name']: payload['metadata']['namespace'] for payload in payloads} == {
            'accounts': 'ws-example',
            'billing': 'ws-example',
        }

    def test_passes_the_namespace_as_an_argument_as_well_as_in_the_body(self):
        # kubectl accepts the redundancy while the two agree, and errors loudly
        # when they do not, rather than silently using the body's namespace.
        with mock.patch.object(aliases.sh, 'kubectl') as kubectl:
            with mock.patch.object(aliases.sh, 'echo'):
                aliases.apply('ws-example', ['accounts'])

        assert kubectl.call_args[0][1:] == ('apply', '--namespace', 'ws-example', '-f', '-')

    def test_emits_no_namespace_argument_when_no_workspace_is_active(self):
        with mock.patch.object(aliases.sh, 'kubectl') as kubectl:
            with mock.patch.object(aliases.sh, 'echo'):
                aliases.apply('', ['accounts'])

        assert '--namespace' not in kubectl.call_args[0]

    def test_applies_nothing_for_an_empty_list(self):
        with mock.patch.object(aliases.sh, 'kubectl') as kubectl:
            aliases.apply('ws-example', [])

        kubectl.assert_not_called()


class TestSync:
    def test_reconciles_and_applies_and_deletes(self):
        with mock.patch.object(aliases, 'list_shared_services', return_value={'accounts', 'billing'}):
            with mock.patch.object(aliases, 'list_real_services', return_value={'accounts'}):
                with mock.patch.object(aliases, 'list_aliases', return_value={'accounts'}):
                    with mock.patch.object(aliases, 'apply') as apply:
                        with mock.patch.object(aliases, 'delete') as delete:
                            result = aliases.sync('ws-example')

        apply.assert_called_once_with('ws-example', ['billing'])
        delete.assert_called_once_with('ws-example', ['accounts'])
        assert result == aliases.Reconciliation(['billing'], ['accounts'])


class TestSyncRefusesToReconcileFromAFailedListing:
    """
    A transient kubectl failure used to make sync delete the workspace's whole
    DNS overlay: an empty "shared services" set makes every existing alias look
    retired, and the command then printed "removed N" as though that were the
    reconciliation the user asked for.
    """

    listing_failed = aliases.ServiceListingFailed('kubectl is unhappy')

    def test_a_failing_shared_listing_deletes_nothing(self):
        with mock.patch.object(aliases, 'list_shared_services', side_effect=self.listing_failed):
            with mock.patch.object(aliases, 'list_real_services', return_value=set()):
                with mock.patch.object(aliases, 'list_aliases', return_value={'accounts', 'billing'}):
                    with mock.patch.object(aliases, 'apply') as apply:
                        with mock.patch.object(aliases, 'delete') as delete:
                            with pytest.raises(aliases.ServiceListingFailed):
                                aliases.sync('ws-example')

        delete.assert_not_called()
        apply.assert_not_called()

    def test_a_failing_workspace_listing_deletes_nothing_either(self):
        with mock.patch.object(aliases, 'list_shared_services', return_value={'accounts'}):
            with mock.patch.object(aliases, 'list_real_services', side_effect=self.listing_failed):
                with mock.patch.object(aliases, 'apply') as apply:
                    with mock.patch.object(aliases, 'delete') as delete:
                        with pytest.raises(aliases.ServiceListingFailed):
                            aliases.sync('ws-example')

        delete.assert_not_called()
        apply.assert_not_called()

    def test_the_failure_reaches_the_caller_rather_than_an_empty_reconciliation(self):
        # sync must not return a Reconciliation the caller would go on to
        # print as "created 0, removed N".
        with mock.patch.object(aliases, 'list_shared_services', side_effect=self.listing_failed):
            with mock.patch.object(aliases, 'list_aliases', return_value={'accounts'}):
                with mock.patch.object(aliases, 'delete'):
                    with pytest.raises(aliases.ServiceListingFailed):
                        aliases.sync('ws-example')
