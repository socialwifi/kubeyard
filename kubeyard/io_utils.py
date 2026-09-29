def default_input(prompt, default):
    value = input('{} [{}]: '.format(prompt, default))
    return value or default


def required_input(prompt):
    while True:
        value = input('{}: '.format(prompt)).strip()
        if value:
            return value
