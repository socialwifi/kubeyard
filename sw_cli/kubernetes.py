import contextlib
import socket

import sh

from sw_cli import base_command
from sw_cli import minikube


class Kubernetes:
    def setup_cluster_context(self):
        monolith_host = self._get_my_ip_address()
        minikube.ensure_minikube_started()
        with contextlib.suppress(sh.ErrorReturnCode):
            sh.kubectl('delete', 'configmap', 'monolith')
        sh.kubectl('create', 'configmap', 'monolith', '--from-literal', 'host={}'.format(monolith_host))

    @staticmethod
    def _get_my_ip_address():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
