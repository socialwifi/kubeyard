import contextlib
import socket

import sh

from sw_cli import base_command


def setup_cluster_context():
    KubernetesCommand().setup_cluster_context()


class KubernetesCommand(base_command.BaseCommand):
    def setup_cluster_context(self):
        print("only development environment is currently supported!")
        monolith_host = self._get_my_ip_address()
        with contextlib.suppress(sh.ErrorReturnCode):
            sh.kubectl('delete', 'configmap', 'monolith')
        sh.kubectl('create', 'configmap', 'monolith', '--from-literal', 'host={}'.format(monolith_host))
        print('done')

    @staticmethod
    def _get_my_ip_address():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
