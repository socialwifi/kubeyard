from argparse import ArgumentParser
import pathlib


import sw_cli.files_generator
from sw_cli import context_factories


def run(args):
    print("initialising repo")
    options = parse_arguments(args)
    project_dst = pathlib.Path(options.directory)
    context = context_factories.EmptyRepoContextFactory(options.directory).get()
    sw_cli.files_generator.copy_template('new_repository', project_dst, context=context)
    print('done')


def parse_arguments(args):
    parser = ArgumentParser()
    parser.add_argument("--directory", dest="directory", default=".", help="Select project root directory.")
    return parser.parse_args(args)
