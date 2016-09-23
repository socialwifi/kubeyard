#!/usr/bin/env python

import pkg_resources
import sys

def run():
    sys.stdout.write(' '.join(get_script_names()))


def get_script_names():
    for console_script in pkg_resources.iter_entry_points(group='console_scripts'):
        yield console_script.name


if __name__ == '__main__':
    run()
