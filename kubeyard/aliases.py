import collections
import json
import logging

import sh

from kubeyard import kubectl as kubectl_helper
from kubeyard import workspace

logger = logging.getLogger(__name__)

ALIAS_LABEL = 'kubeyard.io/alias'

Reconciliation = collections.namedtuple('Reconciliation', ['to_create', 'to_delete'])


def reconcile(shared_services, real_services, existing_aliases) -> Reconciliation:
    """
    Decide which aliases to create and which to remove.

    Only names already present in existing_aliases can ever be deleted, which
    is what guarantees a real deployment is never removed by alias housekeeping.
    """
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
    except sh.ErrorReturnCode:
        return set()
    return set(output.split()) if output else set()


def list_shared_services():
    return _service_names(workspace.DEFAULT_NAMESPACE)


def list_services(namespace):
    return _service_names(namespace)


def list_aliases(namespace):
    return _service_names(namespace, selector='{}=true'.format(ALIAS_LABEL))


def list_real_services(namespace):
    return list_services(namespace) - list_aliases(namespace)


def apply(namespace, names):
    for name in names:
        definition = alias_definition(name, namespace)
        sh.kubectl(sh.echo(json.dumps(definition)), 'apply', '-f', '-')
        logger.debug('Alias created for "{}" in "{}"'.format(name, namespace))


def delete(namespace, names):
    """
    Delete alias Services by name.

    kubectl refuses to combine a resource name with --selector, so the label
    guard is applied here: only names that are currently labelled as aliases in
    this namespace are deleted. A real Service passed in by mistake is ignored.
    """
    deletable = set(names) & list_aliases(namespace)
    for name in sorted(deletable):
        sh.kubectl('delete', 'service', name, *kubectl_helper.namespace_args(namespace),
                   '--ignore-not-found')
        logger.debug('Alias removed for "{}" in "{}"'.format(name, namespace))
    for name in sorted(set(names) - deletable):
        logger.debug('Not an alias, left alone: "{}" in "{}"'.format(name, namespace))


def sync(namespace):
    result = reconcile(
        shared_services=list_shared_services(),
        real_services=list_real_services(namespace),
        existing_aliases=list_aliases(namespace),
    )
    apply(namespace, result.to_create)
    delete(namespace, result.to_delete)
    return result
