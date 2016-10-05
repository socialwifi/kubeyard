def default_input(prompt, default):
    value = input('{} [{}]: '.format(prompt, default))
    return value or default
