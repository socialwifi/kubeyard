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
    kubectl could not list Services, so their absence cannot be inferred.

    Reconciliation reads "not in the shared namespace" as "retired, delete the
    alias", so a listing that silently came back empty because the call failed
    would delete a workspace's entire DNS overlay and report it as the
    intended reconciliation.
    """


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
    except sh.ErrorReturnCode as e:
        raise ServiceListingFailed(
            'Could not list Services in namespace "{}". Refusing to treat a failed listing as an empty '
            'one; re-run once kubectl works again.'.format(namespace or workspace.DEFAULT_NAMESPACE)) from e
    return set(output.split()) if output else set()


def never_aliased_services() -> set:
    """
    Services that must never be aliased back to the shared namespace.

    A workspace runs its own copy of every development requirement kubeyard
    provisions, so an ExternalName alias of the same name would shadow it: the
    workspace's own Postgres or RabbitMQ would become unreachable and
    migrations, seeds and workers would silently address the shared instance
    instead. The cluster's own API Service must never be shadowed either.

    The requirement names are read from the requirement registry rather than
    listed here, so adding a development requirement cannot leave this stale.
    The import is deferred: kubeyard.commands.dev_requirements lives in the
    commands package, whose __init__ imports commands.deploy, which imports
    this module - a module-level import would close that loop.
    """
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
        # The namespace is in the definition already; passing it as an argument
        # too is what makes a disagreement between the two an error kubectl
        # reports rather than one it silently resolves in favour of the body.
        sh.kubectl(sh.echo(json.dumps(definition)), 'apply',
                   *kubectl_helper.namespace_args(namespace), '-f', '-')
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
    """
    Reconcile the alias overlay, or do nothing at all.

    Every listing is taken before the first write, so a ServiceListingFailed
    from any of them aborts the whole reconciliation rather than deleting
    aliases that only look retired because kubectl could not answer.
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
