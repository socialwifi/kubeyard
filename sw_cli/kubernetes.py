import contextlib
import socket

import sh

from sw_cli import base_command
from sw_cli import minikube


def setup_cluster_context(context):
    if context['SWCLI_MODE'] == 'development':
        DevelopmentKubernetesContext().setup()
    else:
        ProductionKubernetesContext().setup()


class BaseKubernetesContext:
    def setup(self):
        with contextlib.suppress(sh.ErrorReturnCode):
            sh.kubectl('delete', 'configmap', 'monolith')
        sh.kubectl('create', 'configmap', 'monolith', '--from-literal', 'host={}'.format(self.monolith_host))

    @property
    def monolith_host(self):
        raise NotImplementedError


class DevelopmentKubernetesContext(BaseKubernetesContext):
    def setup(self):
        minikube.ensure_minikube_started()
        super().setup()

    @property
    def monolith_host(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]


class ProductionKubernetesContext(BaseKubernetesContext):
    monolith_host = 'socialwifi.com'
