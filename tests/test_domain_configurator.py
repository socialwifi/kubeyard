from unittest import mock

import pytest

from kubeyard.commands import deploy


def context(workspace=''):
    return {
        'KUBEYARD_WORKSPACE': workspace,
        'DEV_TLD': 'example.test',
        'DEV_DOMAINS': ['frontend', 'api'],
    }


class TestDomainsFor:
    def test_without_workspace_uses_plain_domains(self):
        configurator = deploy.DomainConfigurator(context())

        assert configurator.domains_for('') == ['frontend.example.test', 'api.example.test']

    def test_with_workspace_inserts_workspace_and_ws_label(self):
        configurator = deploy.DomainConfigurator(context('example'))

        assert configurator.domains_for('example') == [
            'frontend.example.ws.example.test',
            'api.example.ws.example.test',
        ]

    def test_active_workspace_is_used_by_default(self):
        configurator = deploy.DomainConfigurator(context('example'))

        assert configurator.all_domains == [
            'frontend.example.ws.example.test',
            'api.example.ws.example.test',
        ]

    def test_empty_dev_domains_yields_nothing(self):
        configurator = deploy.DomainConfigurator({
            'KUBEYARD_WORKSPACE': 'example', 'DEV_TLD': 'example.test', 'DEV_DOMAINS': []})

        assert configurator.domains_for('example') == []

    def test_explicit_argument_overrides_active_workspace(self):
        # domains_for takes an explicit workspace name; it must not silently
        # fall back to context['KUBEYARD_WORKSPACE'] instead of using it.
        configurator = deploy.DomainConfigurator(context('example'))

        assert configurator.domains_for('') == ['frontend.example.test', 'api.example.test']

    def test_all_domains_without_active_workspace_uses_plain_domains(self):
        configurator = deploy.DomainConfigurator(context())

        assert configurator.all_domains == ['frontend.example.test', 'api.example.test']


class TestCustomDomainsToBeConfiguredBackwardCompatibility:
    """
    Non-workspace behaviour of the pre-existing property must not change.
    """

    def test_filters_domains_already_present_in_hosts_without_workspace(self, tmp_path):
        hosts_path = tmp_path / 'hosts'
        hosts_path.write_text(
            '# The following line is added by kubeyard\n'
            '10.0.0.1\tfrontend.example.test\n',
        )
        configurator = deploy.DomainConfigurator(context())
        configurator.hosts_filename = str(hosts_path)

        assert configurator.custom_domains_to_be_configured == ['api.example.test']

    def test_filters_domains_already_present_in_hosts_with_workspace(self, tmp_path):
        hosts_path = tmp_path / 'hosts'
        hosts_path.write_text(
            '# The following line is added by kubeyard\n'
            '10.0.0.1\tfrontend.example.ws.example.test\n',
        )
        configurator = deploy.DomainConfigurator(context('example'))
        configurator.hosts_filename = str(hosts_path)

        assert configurator.custom_domains_to_be_configured == ['api.example.ws.example.test']


class TestRemove:
    def test_empty_workspace_name_is_refused(self, tmp_path):
        # remove('') would otherwise resolve to the plain, non-workspace
        # domains and strip the shared /etc/hosts entries: the "destroy can
        # never target the shared namespace" invariant only holds upstream,
        # so this method must not silently trust an empty name either.
        configurator = deploy.DomainConfigurator(context())
        configurator.hosts_filename = str(tmp_path / 'hosts')

        with mock.patch.object(deploy.sh, 'sudo') as sudo:
            with pytest.raises(ValueError):
                configurator.remove('')

        sudo.assert_not_called()

    def test_no_domains_does_not_touch_hosts_file(self, tmp_path):
        configurator = deploy.DomainConfigurator({
            'KUBEYARD_WORKSPACE': '', 'DEV_TLD': 'example.test', 'DEV_DOMAINS': []})
        configurator.hosts_filename = str(tmp_path / 'hosts')

        with mock.patch.object(deploy.sh, 'sudo') as sudo:
            configurator.remove('example')

        sudo.assert_not_called()

    def test_no_matching_entries_does_not_touch_hosts_file(self, tmp_path):
        hosts_path = tmp_path / 'hosts'
        hosts_path.write_text('127.0.0.1\tlocalhost\n')
        configurator = deploy.DomainConfigurator(context())
        configurator.hosts_filename = str(hosts_path)

        with mock.patch.object(deploy.sh, 'sudo') as sudo:
            configurator.remove('example')

        sudo.assert_not_called()

    def test_reports_how_many_entries_went_away_not_how_many_lines(self, tmp_path, caplog):
        """
        Each entry occupies two lines - the watermark comment and the mapping
        itself - so counting lines doubles the number, and the count a
        developer cares about is how many domains stopped resolving.
        """
        hosts_path = tmp_path / 'hosts'
        hosts_path.write_text(
            '127.0.0.1\tlocalhost\n'
            '# The following line is added by kubeyard\n'
            '10.0.0.1\tfrontend.example.ws.example.test\n'
            '# The following line is added by kubeyard\n'
            '10.0.0.1\tapi.example.ws.example.test\n',
        )
        configurator = deploy.DomainConfigurator(context())
        configurator.hosts_filename = str(hosts_path)

        with mock.patch.object(deploy.sh, 'sudo'):
            with mock.patch.object(deploy.getpass, 'getpass', return_value=''):
                with caplog.at_level('INFO'):
                    configurator.remove('example')

        assert any('Removing 2 host entries' in record.message for record in caplog.records)

    def test_removes_only_this_workspace_domains(self, tmp_path):
        hosts_path = tmp_path / 'hosts'
        hosts_path.write_text(
            '127.0.0.1\tlocalhost\n'
            '# The following line is added by kubeyard\n'
            '10.0.0.1\tfrontend.example.ws.example.test\n'
            '# The following line is added by kubeyard\n'
            '10.0.0.1\tapi.example.ws.example.test\n'
            '# The following line is added by kubeyard\n'
            '10.0.0.1\tfrontend.other.ws.example.test\n'
            '10.0.0.9\tfrontend.example.test\thand-added\n',
        )
        configurator = deploy.DomainConfigurator(context())
        configurator.hosts_filename = str(hosts_path)
        configurator._sudo_password = 'secret\n'

        with mock.patch.object(deploy.sh, 'sudo') as sudo:
            configurator.remove('example')

        sudo.assert_called_once()
        written = sudo.call_args.kwargs['_in']
        assert written.startswith('secret\n')
        assert 'frontend.example.ws.example.test' not in written
        assert 'api.example.ws.example.test' not in written
        # another workspace's entry (and its own watermark) is untouched
        assert 'frontend.other.ws.example.test' in written
        assert written.count('# The following line is added by kubeyard') == 1
        # a hand-added entry that is not a workspace domain is untouched
        assert 'frontend.example.test\thand-added' in written
        assert 'localhost' in written

    def test_is_idempotent_on_a_second_run(self, tmp_path):
        hosts_path = tmp_path / 'hosts'
        hosts_path.write_text(
            '127.0.0.1\tlocalhost\n'
            '# The following line is added by kubeyard\n'
            '10.0.0.1\tfrontend.other.ws.example.test\n',
        )
        configurator = deploy.DomainConfigurator(context())
        configurator.hosts_filename = str(hosts_path)

        with mock.patch.object(deploy.sh, 'sudo') as sudo:
            configurator.remove('example')

        sudo.assert_not_called()
