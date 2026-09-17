import collections
import json
import logging

import sh

from kubeyard import kubectl as kubectl_helper
from kubeyard import workspace

logger = logging.getLogger(__name__)

ALIAS_LABEL = 'kubeyard.io/alias'
KUBERNETES_API_SERVICE = 'kubernetes'

Reconciliation = collections.namedtuple('Reconciliation', ['to_create', 'to_delete'])


class ServiceListingFailed(Exception):
    """
    Reconciliation reads "absent from the shared namespace" as "retired, delete the
    alias", so a failed listing must never be mistaken for an empty one.
    """


def reconcile(shared_services, real_services, existing_aliases) -> Reconciliation:
    wanted = set(shared_services) - set(real_services)
    to_create = wanted - set(existing_aliases)
    to_delete = set(existing_aliases) - wanted
    return Reconciliation(sorted(to_create), sorted(to_delete))


def alias_definition(name, namespace) -> dict:
    return {
        'apiVersion': 'v1',
        'kind': 'Service',
        'metadata': {
            'name': name,
            'namespace': namespace,
            'labels': {ALIAS_LABEL: 'true'},
        },
        'spec': {
            'type': 'ExternalName',
            'externalName': '{}.{}.svc.cluster.local'.format(name, workspace.DEFAULT_NAMESPACE),
        },
    }


def _service_names(namespace, selector=None):
    command = ['get', 'services', *kubectl_helper.namespace_args(namespace),
               '--output', 'jsonpath={.items[*].metadata.name}']
    if selector is not None:
        command += ['--selector', selector]
    try:
        output = str(sh.kubectl(*command)).strip()
    except sh.ErrorReturnCode as e:
        raise ServiceListingFailed(
            'Could not list Services in namespace "{}". Refusing to treat a failed listing as an empty '
            'one; re-run once kubectl works again.'.format(namespace or workspace.DEFAULT_NAMESPACE)) from e
    return set(output.split()) if output else set()


def never_aliased_services() -> set:
    """
    Aliasing these would shadow the workspace's own copy, so its Postgres or RabbitMQ
    would become unreachable and migrations and seeds would silently address the
    shared instance instead.
    """
    # Deferred: commands/__init__ imports deploy, which imports this module.
    from kubeyard.commands import dev_requirements
    return dev_requirements.provided_service_names() | {KUBERNETES_API_SERVICE}


def list_shared_services():
    return _service_names(workspace.DEFAULT_NAMESPACE) - never_aliased_services()


def list_services(namespace):
    return _service_names(namespace)


def list_aliases(namespace):
    return _service_names(namespace, selector='{}=true'.format(ALIAS_LABEL))


def list_real_services(namespace):
    return list_services(namespace) - list_aliases(namespace)


def apply(namespace, names):
    for name in names:
        definition = alias_definition(name, namespace)
        # Passing the namespace as well as setting it in the body makes any
        # disagreement between them an error rather than a silent resolution.
        sh.kubectl(sh.echo(json.dumps(definition)), 'apply',
                   *kubectl_helper.namespace_args(namespace), '-f', '-')
        logger.debug('Alias created for "{}" in "{}"'.format(name, namespace))


def delete(namespace, names):
    """
    kubectl refuses to combine a resource name with --selector, so the label guard
    is applied here instead: a real Service passed in by mistake is left alone.
    """
    deletable = set(names) & list_aliases(namespace)
    for name in sorted(deletable):
        sh.kubectl('delete', 'service', name, *kubectl_helper.namespace_args(namespace),
                   '--ignore-not-found')
        logger.debug('Alias removed for "{}" in "{}"'.format(name, namespace))
    for name in sorted(set(names) - deletable):
        logger.debug('Not an alias, left alone: "{}" in "{}"'.format(name, namespace))


def sync(namespace):
    """
    Every listing happens before the first write, so a ServiceListingFailed aborts
    the whole reconciliation rather than deleting aliases mid-way.
    """
    shared_services = list_shared_services()
    real_services = list_real_services(namespace)
    existing_aliases = list_aliases(namespace)
    result = reconcile(
        shared_services=shared_services,
        real_services=real_services,
        existing_aliases=existing_aliases,
    )
    apply(namespace, result.to_create)
    delete(namespace, result.to_delete)
    return result
