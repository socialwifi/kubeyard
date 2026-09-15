import logging

import sh

logger = logging.getLogger(__name__)


def allocated_node_ports() -> dict:
    """Map every nodePort allocated in the cluster to its "<namespace>/<name>" owner."""
    template = (
        '{range .items[*]}{.metadata.namespace}/{.metadata.name}'
        '{range .spec.ports[*]} {.nodePort}{end}\n{end}'
    )
    try:
        output = str(sh.kubectl('get', 'services', '--all-namespaces', '--output', 'jsonpath=' + template))
    except sh.ErrorReturnCode:
        return {}
    allocated = {}
    for line in output.splitlines():
        parts = line.split()
        if not parts:
            continue
        owner = parts[0]
        for port in parts[1:]:
            if port.isdigit():
                allocated[int(port)] = owner
    return allocated


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _fixed_node_ports(definition):
    if not isinstance(definition, dict):
        return []
    if definition.get('kind') != 'Service':
        return []
    spec = definition.get('spec') or {}
    ports = spec.get('ports') or []
    if not isinstance(ports, list):
        return []
    return [
        port.get('nodePort') for port in ports
        if isinstance(port, dict) and port.get('nodePort')
    ]


def _own_identity(definition, namespace):
    metadata = definition.get('metadata') or {}
    return '{}/{}'.format(namespace, metadata.get('name'))


def should_skip(definition, allocated, namespace) -> bool:
    if not isinstance(definition, dict):
        return False
    own_identity = _own_identity(definition, namespace)
    for node_port in _fixed_node_ports(definition):
        port_number = _as_int(node_port)
        if port_number is None:
            continue
        holder = allocated.get(port_number)
        if holder is not None and holder != own_identity:
            return True
    return False


def skip_reason(definition, allocated, namespace) -> str:
    if not isinstance(definition, dict):
        return ''
    metadata = definition.get('metadata') or {}
    name = metadata.get('name')
    own_identity = _own_identity(definition, namespace)
    for node_port in _fixed_node_ports(definition):
        port_number = _as_int(node_port)
        if port_number is None:
            continue
        holder = allocated.get(port_number)
        if holder is not None and holder != own_identity:
            return (
                'Skipping Service/{name}: fixed nodePort {port} is cluster-global and already '
                'allocated by {holder}. Pick an unused port in this worktree to enable it, or '
                'ignore this - the application itself is served through kube-nginx as '
                'normal.'.format(name=name, port=port_number, holder=holder)
            )
    return ''


def skip_predicate(allocated, namespace):
    """
    Build the predicate handed to kubepy's apply_all(skip=...).

    Deliberately pure: it decides, it does not log. kubepy logs the fact of a
    skip at INFO from inside its own generator, and `deploy` reports the reason
    at WARNING before applying. Logging here as well would emit two lines for
    one event, and a predicate that raises mid-generator would abort a deploy
    with some definitions already applied.
    """
    def skip(definition):
        return should_skip(definition, allocated, namespace)
    return skip
