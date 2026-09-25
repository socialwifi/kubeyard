import collections
import pathlib
import re

MARKER_FILENAME = '.kubeyard-workspace'
NAMESPACE_PREFIX = 'ws-'
DOMAIN_SEGMENT = 'ws'
DEFAULT_NAMESPACE = 'default'
WORKSPACE_ENVIRONMENT_VARIABLE = 'KUBEYARD_WORKSPACE'
MAX_NAME_LENGTH = 30

Workspace = collections.namedtuple('Workspace', ['name', 'namespace'])

INACTIVE = Workspace('', '')


class InvalidWorkspaceName(Exception):
    pass


def normalize_name(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')


def validate_name(name: str) -> str:
    normalized = normalize_name(name)
    if not normalized:
        raise InvalidWorkspaceName(
            'Workspace name {!r} is empty after normalization. '
            'Use lowercase letters, digits and dashes.'.format(name))
    if len(normalized) > MAX_NAME_LENGTH:
        raise InvalidWorkspaceName(
            'Workspace name {!r} normalizes to {!r}, which is {} characters; '
            'the maximum is {}.'.format(name, normalized, len(normalized), MAX_NAME_LENGTH))
    return normalized


def namespace_for(name: str) -> str:
    return NAMESPACE_PREFIX + name


def marker_path(project_dir) -> pathlib.Path:
    return pathlib.Path(project_dir) / MARKER_FILENAME


def read_marker(project_dir) -> str:
    path = marker_path(project_dir)
    if path.exists():
        return path.read_text().strip()
    else:
        return ''


def write_marker(project_dir, name: str) -> None:
    marker_path(project_dir).write_text(name + '\n')


def remove_marker(project_dir) -> None:
    marker_path(project_dir).unlink(missing_ok=True)


def resolve(project_dir, environ) -> Workspace:
    """
    Resolve the active workspace for a project directory.

    Priority: the KUBEYARD_WORKSPACE environment variable (an empty value
    explicitly forces the shared environment), then the marker file, then
    inactive.
    """
    if WORKSPACE_ENVIRONMENT_VARIABLE in environ:
        raw_name = environ[WORKSPACE_ENVIRONMENT_VARIABLE]
    else:
        raw_name = read_marker(project_dir)
    if not raw_name.strip():
        return INACTIVE
    name = validate_name(raw_name)
    return Workspace(name, namespace_for(name))
