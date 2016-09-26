#!/usr/bin/env python

import optparse
import pathlib
import sw_cli.files_generator

def run():
    installation_directory = pathlib.Path('/installation')
    if installation_directory.is_dir():
        print("installing sw-cli")
        options, args = parse_arguments()
        sw_cli_destination = installation_directory / 'sw-cli'
        context = {'development_directory': options.development_directory,}
        sw_cli.files_generator.copy_template('sw-cli.sh.template', sw_cli_destination, context=context, replace=True)
        sw_cli_destination.chmod(0o755)
        print('done')
    else:
        print('Add option "-v /usr/bin:/installation" to docker run command.')


def parse_arguments():
    parser = optparse.OptionParser()
    parser.add_option("--development-dir", dest="development_directory", help="Installs.")
    return parser.parse_args()


if __name__ == '__main__':
    run()
