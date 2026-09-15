from unittest import mock

from kubeyard import node_ports


def service(name, node_port=None, service_type='ClusterIP'):
    port = {'port': 80, 'targetPort': 80}
    if node_port is not None:
        port['nodePort'] = node_port
    return {
        'apiVersion': 'v1',
        'kind': 'Service',
        'metadata': {'name': name},
        'spec': {'type': service_type, 'ports': [port]},
    }


ALLOCATED = {30555: 'default/frontend-livereload'}


class TestShouldSkip:
    def test_service_without_node_port_is_never_skipped(self):
        assert node_ports.should_skip(service('frontend'), ALLOCATED, 'ws-example') is False

    def test_service_with_free_node_port_is_not_skipped(self):
        assert node_ports.should_skip(
            service('frontend-livereload', node_port=30655),
            ALLOCATED, 'ws-example') is False

    def test_service_with_port_held_elsewhere_is_skipped(self):
        assert node_ports.should_skip(
            service('frontend-livereload', node_port=30555),
            ALLOCATED, 'ws-example') is True

    def test_port_held_by_the_same_service_counts_as_free(self):
        allocated = {30555: 'ws-example/frontend-livereload'}

        assert node_ports.should_skip(
            service('frontend-livereload', node_port=30555),
            allocated, 'ws-example') is False

    def test_non_service_kinds_are_never_skipped(self):
        deployment = {'kind': 'Deployment', 'metadata': {'name': 'frontend'}}

        assert node_ports.should_skip(deployment, ALLOCATED, 'ws-example') is False

    def test_service_without_spec_ports_is_not_skipped(self):
        definition = {'kind': 'Service', 'metadata': {'name': 'x'}, 'spec': {}}

        assert node_ports.should_skip(definition, ALLOCATED, 'ws-example') is False


class TestShouldSkipIsTotal:
    """
    should_skip is called from inside kubepy's apply generator while
    definitions are being applied one at a time, so it must never raise -
    an exception part-way through would leave a half-applied deploy.
    """

    def test_missing_spec_is_not_skipped(self):
        definition = {'kind': 'Service', 'metadata': {'name': 'x'}}

        assert node_ports.should_skip(definition, ALLOCATED, 'ws-example') is False

    def test_missing_metadata_does_not_raise(self):
        # No name to identify itself with, so it cannot be recognised as the
        # same Service that already holds the port - the conflict is real.
        definition = {'kind': 'Service', 'spec': {'ports': [{'port': 80, 'nodePort': 30555}]}}

        assert node_ports.should_skip(definition, ALLOCATED, 'ws-example') is True

    def test_missing_kind_is_not_skipped(self):
        definition = {'metadata': {'name': 'x'}, 'spec': {'ports': [{'port': 80, 'nodePort': 30555}]}}

        assert node_ports.should_skip(definition, ALLOCATED, 'ws-example') is False

    def test_ports_not_a_list_is_not_skipped(self):
        definition = {'kind': 'Service', 'metadata': {'name': 'x'}, 'spec': {'ports': 'oops'}}

        assert node_ports.should_skip(definition, ALLOCATED, 'ws-example') is False

    def test_port_entry_not_a_dict_is_not_skipped(self):
        definition = {'kind': 'Service', 'metadata': {'name': 'x'}, 'spec': {'ports': ['oops']}}

        assert node_ports.should_skip(definition, ALLOCATED, 'ws-example') is False

    def test_malformed_node_port_value_is_not_skipped(self):
        definition = service('frontend-livereload', node_port='not-a-number')

        assert node_ports.should_skip(definition, ALLOCATED, 'ws-example') is False

    def test_none_node_port_value_is_not_skipped(self):
        definition = {
            'kind': 'Service',
            'metadata': {'name': 'x'},
            'spec': {'ports': [{'port': 80, 'nodePort': None}]},
        }

        assert node_ports.should_skip(definition, ALLOCATED, 'ws-example') is False

    def test_none_definition_is_not_skipped(self):
        # yaml.safe_load of an empty or comment-only file returns None, and
        # kubepy's apply_all calls skip(definition) with whatever that is.
        assert node_ports.should_skip(None, ALLOCATED, 'ws-example') is False

    def test_list_definition_is_not_skipped(self):
        assert node_ports.should_skip([], ALLOCATED, 'ws-example') is False

    def test_string_definition_is_not_skipped(self):
        assert node_ports.should_skip('not a definition', ALLOCATED, 'ws-example') is False

    def test_int_definition_is_not_skipped(self):
        assert node_ports.should_skip(42, ALLOCATED, 'ws-example') is False


class TestSkipReason:
    def test_names_the_service_port_and_holder(self):
        reason = node_ports.skip_reason(
            service('frontend-livereload', node_port=30555),
            ALLOCATED, 'ws-example')

        assert 'frontend-livereload' in reason
        assert '30555' in reason
        assert 'default/frontend-livereload' in reason

    def test_is_empty_when_not_skipped(self):
        reason = node_ports.skip_reason(service('frontend'), ALLOCATED, 'ws-example')

        assert reason == ''

    def test_is_total_for_malformed_definitions(self):
        definition = {'kind': 'Service', 'metadata': {'name': 'x'}, 'spec': {'ports': 'oops'}}

        assert node_ports.skip_reason(definition, ALLOCATED, 'ws-example') == ''

    def test_none_definition_is_empty_reason(self):
        assert node_ports.skip_reason(None, ALLOCATED, 'ws-example') == ''

    def test_list_definition_is_empty_reason(self):
        assert node_ports.skip_reason([], ALLOCATED, 'ws-example') == ''

    def test_string_definition_is_empty_reason(self):
        assert node_ports.skip_reason('not a definition', ALLOCATED, 'ws-example') == ''

    def test_int_definition_is_empty_reason(self):
        assert node_ports.skip_reason(42, ALLOCATED, 'ws-example') == ''


class TestSkipPredicate:
    def test_returns_a_callable_usable_as_skip(self):
        predicate = node_ports.skip_predicate(ALLOCATED, 'ws-example')

        assert predicate(service('frontend-livereload', node_port=30555)) is True
        assert predicate(service('frontend')) is False

    def test_predicate_does_not_raise_on_malformed_definitions(self):
        predicate = node_ports.skip_predicate(ALLOCATED, 'ws-example')

        assert predicate({}) is False

    def test_predicate_does_not_raise_on_a_non_dict_definition(self):
        # yaml.safe_load of an empty or comment-only .yml file is None, and
        # kubepy's apply_all calls skip(definition) on it with no exception
        # handling of its own - a raise here would abort a deploy with some
        # objects already applied.
        predicate = node_ports.skip_predicate(ALLOCATED, 'ws-example')

        assert predicate(None) is False
        assert predicate([]) is False
        assert predicate('not a definition') is False
        assert predicate(42) is False


class TestAllocatedNodePorts:
    def test_maps_port_to_namespace_and_name(self):
        output = 'default/frontend-livereload 30555\nws-example/api 30655\n'

        with mock.patch.object(node_ports.sh, 'kubectl', return_value=output) as kubectl:
            result = node_ports.allocated_node_ports()

        assert result == {30555: 'default/frontend-livereload', 30655: 'ws-example/api'}
        assert '--all-namespaces' in kubectl.call_args[0]
        assert '--namespace' not in kubectl.call_args[0]

    def test_empty_output_is_an_empty_mapping(self):
        with mock.patch.object(node_ports.sh, 'kubectl', return_value=''):
            assert node_ports.allocated_node_ports() == {}

    def test_kubectl_error_is_treated_as_no_allocations(self):
        error = node_ports.sh.ErrorReturnCode('kubectl', b'', b'')
        with mock.patch.object(node_ports.sh, 'kubectl', side_effect=error):
            assert node_ports.allocated_node_ports() == {}

    def test_lines_without_a_port_are_ignored(self):
        with mock.patch.object(node_ports.sh, 'kubectl', return_value='default/web\n'):
            assert node_ports.allocated_node_ports() == {}
