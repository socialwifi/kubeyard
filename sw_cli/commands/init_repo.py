import pathlib
from optparse import OptionParser

import sw_cli.files_generator
from sw_cli import context_factories


def run():
    print("initialising repo")
    options, args = parse_arguments()
    project_dst = pathlib.Path(options.directory)
    context = context_factories.EmptyRepoContextFactory(options.directory).get()
    sw_cli.files_generator.copy_template('new_repository', project_dst, context=context)
    print('done')


def parse_arguments():
    parser = OptionParser()
    parser.add_option("--directory", dest="directory", default=".", help="Select project root directory.")
    return parser.parse_args()
