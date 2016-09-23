#!/usr/bin/env python

from optparse import OptionParser
import os
import pathlib

import sw_cli.files_generator


def run():
    print("initialising repo")
    options, args = parse_arguments()
    project_dst = pathlib.Path(options.directory)
    sw_cli.files_generator.copy_template('new_repository', project_dst)
    uid = int(os.environ['HOST_UID'])
    sw_cli.files_generator.recursive_chown(project_dst, uid)
    print('done')


def parse_arguments():
    parser = OptionParser()
    parser.add_option("--directory", dest="directory", default=".", help="Select project root directory.")
    return parser.parse_args()


if __name__ == '__main__':
    run()
