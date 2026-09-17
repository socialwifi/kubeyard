def namespace_args(namespace):
    """
    Build the kubectl namespace arguments for a workspace namespace.

    Returns an empty tuple when no workspace is active, so that commands are
    byte-identical to the pre-workspace behaviour and continue to honour the
    namespace configured in the user's kubectl context.
    """
    if namespace:
        return ('--namespace', namespace)
    else:
        return ()
