import contextlib
import getpass
import os
import pathlib

from unittest import mock

import pytest

from kubeyard.commands import deploy


class StagedWrite:
    """Records what a mocked sudo was asked to copy into place."""

    content = None
    source_path = None
    calls = ()


@contextlib.contextmanager
def capturing_sudo():
    """
    Stand in for sudo, capturing the file the configurator asked it to copy.

    The real command never sees a password: it copies a temporary file
    straight onto the hosts file, truncating it in place, with the real
    terminal attached so sudo can prompt normally if it needs to.
    """
    staged = StagedWrite()

    def fake_sudo(*args, **kwargs):
        if args[0] == 'cp':
            staged.source_path = args[1]
            staged.content = pathlib.Path(args[1]).read_text()
        return ''

    with mock.patch.object(deploy.sh, 'sudo', side_effect=fake_sudo) as sudo:
        yield staged
    staged.calls = sudo.call_args_list


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

        with capturing_sudo() as staged:
            configurator.remove('example')

        written = staged.content
        assert 'frontend.example.ws.example.test' not in written
        assert 'api.example.ws.example.test' not in written
        # another workspace's entry (and its own watermark) is untouched
        assert 'frontend.other.ws.example.test' in written
        assert written.count('# The following line is added by kubeyard') == 1
        # a hand-added entry that is not a workspace domain is untouched
        assert 'frontend.example.test\thand-added' in written
        assert 'localhost' in written

    def test_never_passes_a_password_to_sudo(self, tmp_path):
        # sudo consumes nothing on stdin once its credentials are cached, so a piped
        # password would land in the world-readable file itself.
        configurator = self._configurator_with_a_removable_entry(tmp_path)

        with capturing_sudo() as staged:
            configurator.remove('example')

        assert staged.calls
        for call in staged.calls:
            assert '-S' not in call.args
            assert '_in' not in call.kwargs

    def test_sudo_runs_in_the_foreground_so_it_can_prompt_on_the_real_terminal(self, tmp_path):
        # sh gives sudo no TTY of its own; without _fg=True a real deploy
        # dies with "sudo: a terminal is required to read the password"
        # whenever sudo's credentials are not already cached.
        configurator = self._configurator_with_a_removable_entry(tmp_path)

        with capturing_sudo() as staged:
            configurator.remove('example')

        assert staged.calls
        for call in staged.calls:
            assert call.kwargs.get('_fg') is True

    def test_never_asks_for_a_password_at_all(self, tmp_path):
        configurator = self._configurator_with_a_removable_entry(tmp_path)

        with mock.patch.object(getpass, 'getpass') as getpass_mock:
            with capturing_sudo():
                configurator.remove('example')

        getpass_mock.assert_not_called()

    def test_writes_directly_onto_the_hosts_file_with_a_single_sudo_call(self, tmp_path):
        # cp truncates in place rather than replacing the inode, which preserves
        # permissions and SELinux context without a staging path or restorecon.
        hosts_path = tmp_path / 'hosts'
        configurator = self._configurator_with_a_removable_entry(tmp_path)

        with capturing_sudo() as staged:
            configurator.remove('example')

        assert len(staged.calls) == 1
        assert staged.calls[0].args == ('cp', staged.source_path, str(hosts_path))

    def test_the_temporary_file_is_cleaned_up(self, tmp_path):
        configurator = self._configurator_with_a_removable_entry(tmp_path)

        with capturing_sudo() as staged:
            configurator.remove('example')

        assert not os.path.exists(staged.source_path)

    def _configurator_with_a_removable_entry(self, tmp_path):
        hosts_path = tmp_path / 'hosts'
        hosts_path.write_text(
            '127.0.0.1\tlocalhost\n'
            '# The following line is added by kubeyard\n'
            '10.0.0.1\tfrontend.example.ws.example.test\n',
        )
        configurator = deploy.DomainConfigurator(context())
        configurator.hosts_filename = str(hosts_path)
        return configurator

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


class TestRunUpdateHosts:
    """
    The append path (configure -> run_update_hosts) used to pipe the sudo
    password on stdin to `tee --append`. Whenever sudo's credentials are
    already cached - very common - or the user has NOPASSWD, sudo never
    reads stdin, so the password landed in /etc/hosts itself, in plaintext,
    in a world-readable file. It must now go through the same atomic,
    password-free write as remove().
    """

    def _configurator(self, tmp_path, existing_content='127.0.0.1\tlocalhost\n'):
        hosts_path = tmp_path / 'hosts'
        hosts_path.write_text(existing_content)
        configurator = deploy.DomainConfigurator(context())
        configurator.hosts_filename = str(hosts_path)
        configurator.minikube_ip = '10.0.0.1'
        return configurator

    def test_appends_new_entries_to_the_existing_content(self, tmp_path):
        configurator = self._configurator(tmp_path)

        with capturing_sudo() as staged:
            configurator.run_update_hosts()

        assert staged.content == (
            '127.0.0.1\tlocalhost\n'
            '# The following line is added by kubeyard\n'
            '10.0.0.1\tfrontend.example.test\n'
            '# The following line is added by kubeyard\n'
            '10.0.0.1\tapi.example.test\n'
        )

    def test_never_passes_a_password_to_sudo(self, tmp_path):
        configurator = self._configurator(tmp_path)

        with capturing_sudo() as staged:
            configurator.run_update_hosts()

        assert staged.calls
        for call in staged.calls:
            assert '-S' not in call.args
            assert '_in' not in call.kwargs
            assert 'tee' not in call.args

    def test_sudo_runs_in_the_foreground_so_it_can_prompt_on_the_real_terminal(self, tmp_path):
        configurator = self._configurator(tmp_path)

        with capturing_sudo() as staged:
            configurator.run_update_hosts()

        assert staged.calls
        for call in staged.calls:
            assert call.kwargs.get('_fg') is True

    def test_never_asks_for_a_password_at_all(self, tmp_path):
        configurator = self._configurator(tmp_path)

        with mock.patch.object(getpass, 'getpass') as getpass_mock:
            with capturing_sudo():
                configurator.run_update_hosts()

        getpass_mock.assert_not_called()

    def test_writes_through_the_same_single_sudo_call_as_remove(self, tmp_path):
        hosts_path = tmp_path / 'hosts'
        configurator = self._configurator(tmp_path)

        with capturing_sudo() as staged:
            configurator.run_update_hosts()

        assert len(staged.calls) == 1
        assert staged.calls[0].args == ('cp', staged.source_path, str(hosts_path))
