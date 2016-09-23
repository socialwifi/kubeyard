#!/usr/bin/env python

import pathlib
import sw_cli.files_generator

def run():
    installation_directory = pathlib.Path('/installation')
    if installation_directory.is_dir():
        print("installing sw-cli")
        sw_cli_destination = installation_directory / 'sw-cli'
        sw_cli.files_generator.copy_template('sw-cli.sh', sw_cli_destination)
        sw_cli_destination.chmod(0o755)
        print('done')
    else:
        print('Add option "-v /usr/bin:/installation" to docker run command.')

if __name__ == '__main__':
    run()
