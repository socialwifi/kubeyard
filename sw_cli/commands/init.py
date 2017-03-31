from argparse import ArgumentParser
import pathlib


import sw_cli.files_generator
from sw_cli import context_factories


def run(args):
    print("Initialising repo...")
    options = parse_arguments(args)
    project_dst = pathlib.Path(options.directory)
    context = context_factories.EmptyRepoContextFactory(options.directory).get()
    sw_cli.files_generator.copy_template(options.template_directory, project_dst, context=context)
    print('Done.')


def parse_arguments(args):
    parser = ArgumentParser()
    parser.add_argument("--directory", dest="directory", default=".", help="Select project root directory.")
    parser.add_argument("--ember", dest="template_directory", action='store_const', const='new_ember_repository',
                        default="new_repository", help="Select ember template.")
    return parser.parse_args(args)
