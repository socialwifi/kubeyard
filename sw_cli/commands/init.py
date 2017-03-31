from argparse import ArgumentParser
import pathlib


import sw_cli.files_generator
from sw_cli import context_factories
from sw_cli import settings


def run(args):
    print("Initialising repo...")
    options = parse_arguments(args)
    init_type = options.init_type
    project_dst = pathlib.Path(options.directory)
    context = context_factories.EmptyRepoContextFactory(options.directory, init_type.prompted_context).get()
    sw_cli.files_generator.copy_template(init_type.template_directory, project_dst, context=context)
    print('Done.')


def parse_arguments(args):
    parser = ArgumentParser()
    parser.add_argument("--directory", dest="directory", default=".", help="Select project root directory.")
    parser.add_argument("--ember", dest="init_type", action='store_const', const=EmberInitType,
                        default=PythonPackageInitType, help="Select ember template.")
    return parser.parse_args(args)


class PythonPackageInitType:
    template_directory = 'new_repository'
    prompted_context = [
        context_factories.PromptedContext(
            'KUBE_SERVICE_NAME', 'service name', settings.DEFAULT_KUBE_SERVICE_NAME_PATTERN),
        context_factories.PromptedContext(
            'KUBE_SERVICE_PORT', 'service port', settings.DEFAULT_KUBE_SERVICE_PORT)
    ]


class EmberInitType:
    template_directory = 'new_ember_repository'
    prompted_context = PythonPackageInitType.prompted_context + [
        context_factories.PromptedContext(
            'KUBE_LIVE_RELOAD_PORT', 'live reload development port', settings.DEFAULT_KUBE_LIVE_RELOAD_PORT)
    ]
