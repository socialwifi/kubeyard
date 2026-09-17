import pathlib

import sh

from kubeyard import settings

BRANCH_PREFIX = 'ws-'


class InvalidWorktreeRoot(Exception):
    pass


def resolve_root(explicit_root, context) -> str:
    return explicit_root or context.get('KUBEYARD_WORKTREE_ROOT') or settings.DEFAULT_KUBEYARD_WORKTREE_ROOT


def branch_for(name) -> str:
    return '{}{}'.format(BRANCH_PREFIX, name)


def name_from_branch(branch) -> str:
    """
    Undoes branch_for. Without this a bare "workspace create" inside a worktree
    would name the workspace after branch ws-alice and produce ws-ws-alice.
    """
    if branch.startswith(BRANCH_PREFIX) and branch != BRANCH_PREFIX:
        return branch[len(BRANCH_PREFIX):]
    return branch


def path_for(project_dir, root, name) -> pathlib.Path:
    """
    The root is always interpreted relative to the project, so a worktree cannot
    escape it - which is what keeps it under $HOME, the only path minikube mounts.
    """
    project_dir = pathlib.Path(project_dir)
    path = (project_dir / root / name).resolve()
    if not path.is_relative_to(project_dir.resolve()):
        raise InvalidWorktreeRoot(
            'Worktree root {!r} resolves outside the project directory. It must be a relative path '
            'inside it, because kubeyard requires the project to live under $HOME.'.format(root))
    return path


def _git_path(project_dir, flag) -> pathlib.Path:
    output = str(sh.git('-C', str(project_dir), 'rev-parse', flag)).strip()
    return (pathlib.Path(project_dir) / output).resolve()


def is_main_checkout(project_dir) -> bool:
    return _git_path(project_dir, '--git-dir') == _git_path(project_dir, '--git-common-dir')


def branch_exists(project_dir, branch) -> bool:
    try:
        sh.git('-C', str(project_dir), 'show-ref', '--verify', '--quiet', 'refs/heads/{}'.format(branch))
    except sh.ErrorReturnCode:
        return False
    return True


def ensure(project_dir, path, branch) -> bool:
    """Create the worktree unless it is already there. True if this call created it."""
    if path.exists():
        return False
    if branch_exists(project_dir, branch):
        sh.git('-C', str(project_dir), 'worktree', 'add', str(path), branch)
    else:
        sh.git('-C', str(project_dir), 'worktree', 'add', str(path), '-b', branch)
    return True
