from kubeyard import kubectl


class TestNamespaceArgs:
    def test_empty_namespace_emits_no_arguments(self):
        assert kubectl.namespace_args('') == ()

    def test_none_namespace_emits_no_arguments(self):
        assert kubectl.namespace_args(None) == ()

    def test_namespace_emits_flag_and_value(self):
        assert kubectl.namespace_args('ws-example') == ('--namespace', 'ws-example')

    def test_result_is_splattable_into_a_command(self):
        command = ('get', 'pods') + kubectl.namespace_args('')

        assert command == ('get', 'pods')
