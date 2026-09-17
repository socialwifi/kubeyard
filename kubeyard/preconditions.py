import pathlib

import sh

EXPECTED_KUBECTL_CONTEXT = 'minikube'


class PreconditionFailed(Exception):
    pass


def check_development_mode(context):
    mode = context.get('KUBEYARD_MODE')
    if mode != 'development':
        raise PreconditionFailed(
            'Workspaces are only available in development mode, but KUBEYARD_MODE is {!r}. '
            'Run "kubeyard setup --development" first.'.format(mode))


def check_kubectl_context(current_context, expected=EXPECTED_KUBECTL_CONTEXT):
    if current_context != expected:
        raise PreconditionFailed(
            'Refusing to touch cluster: kubectl context is {!r}, expected {!r}. '
            'Switch with "kubectl config use-context {}".'.format(current_context, expected, expected))


def check_project_dir_under_home(project_dir, home):
    project_dir = pathlib.Path(project_dir).resolve()
    home = pathlib.Path(home).resolve()
    try:
        project_dir.relative_to(home)
    except ValueError:
        raise PreconditionFailed(
            'Project directory {} is outside {}. minikube only mounts $HOME, so host volumes '
            'would silently fail to mount. Move the worktree under your home '
            'directory.'.format(project_dir, home))


def current_kubectl_context() -> str:
    return str(sh.kubectl('config', 'current-context')).strip()


def check_cluster_is_the_expected_one():
    """For commands that only read, and so depend on no other precondition."""
    check_kubectl_context(current_kubectl_context())


def check_all(context, project_dir):
    check_development_mode(context)
    check_kubectl_context(current_kubectl_context())
    check_project_dir_under_home(project_dir, pathlib.Path.home())
