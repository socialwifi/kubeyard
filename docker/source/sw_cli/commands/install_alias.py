#!/usr/bin/env python

import pathlib
import shutil

def run():
    templates_directory = pathlib.Path(__file__).parent.parent / 'templates'
    installation_directory = pathlib.Path('/installation')
    if installation_directory.is_dir():
        print("installing sw-cli")
        sw_cli_destination = installation_directory / 'sw-cli'
        shutil.copy(str(templates_directory / 'sw-cli.sh'), str(sw_cli_destination))
        sw_cli_destination.chmod(0o755)
        print('done')
    else:
        print('Add option "-v /usr/bin:/installation" to docker run command.')

if __name__ == '__main__':
    run()
