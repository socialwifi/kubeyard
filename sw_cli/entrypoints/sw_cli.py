#!/usr/bin/env python
import logging

import click

from sw_cli import settings
from sw_cli.commands.bash_completion import InstallCompletion
from sw_cli.commands.debug import DebugCommand
from sw_cli.commands.devel import BuildCommand
from sw_cli.commands.devel import DeployCommand
from sw_cli.commands.devel import PushCommand
from sw_cli.commands.devel import UpdateRequirementsCommand
from sw_cli.commands.fix_code_style import FixCodeStyle
from sw_cli.commands.global_commands import InstallGlobalSecretsCommand
from sw_cli.commands.global_commands import SetupCommand
from sw_cli.commands.init import InitCommand, EmberInitType, PythonPackageInitType
from sw_cli.commands.jenkins import JenkinsBuildCommand
from sw_cli.commands.jenkins import JenkinsInfoCommand
from sw_cli.commands.jenkins import JenkinsInitCommand
from sw_cli.commands.jenkins import JenkinsReconfigCommand
from sw_cli.commands.test import TestCommand

logger = logging.getLogger(__name__)


@click.group()
@click.version_option()
def cli():
    """
    sw-cli is a commandline tool for easier development and deployment of Social WiFi services.

    If some command allows you to pass additional arguments (for example to pytest),
    you should use double dash `--` to separate it from command args.

    sw-cli [OPTIONS] COMMAND [ARGS] -- [ARGS SHOULD BE PASSED]
    """
    pass


def apply_common_options(options):
    def wrap(func):
        for option in reversed(options):
            func = option(func)
        return func

    return wrap


initialized_repository_options = (
    click.option(
        "--directory",
        default=settings.DEFAULT_SWCLI_PROJECT_DIR,
        type=click.Path(
            file_okay=False,
            exists=True,
            resolve_path=True,
        ),
        help="Select project root directory.",
    ),
    click.option(
        "--verbose",
        "-v",
        "log_level",
        flag_value="DEBUG",
        help="Outputs debug logs.",
    ),
)

devel_options = (
    click.option(
        "--tag",
        help="Used image tag.",
    ),
    click.option(
        "--default",
        "use_default_implementation",
        is_flag=True,
        help="Don't try to execute custom script. Useful when you need original behaviour in overridden method.",
    ),
    click.option(
        "--image-name",
        help="Image name (without repository). Default is set in sw-cli.yml.",
    ),
)


@cli.command(
    help=TestCommand.__doc__,
    context_settings=dict(
        ignore_unknown_options=True,
    ),
)
@apply_common_options(initialized_repository_options)
@apply_common_options(devel_options)
@click.option(
    "--force-migrate-db",
    "-f-m-db",
    "force_migrate_database",
    is_flag=True,
    help="On dev environment DB is cached, so if you have some new migrations, you should use this flag.",
)
@click.option(
    "--force-recreate-db",
    "-f-r-db",
    "force_recreate_database",
    is_flag=True,
    help="On dev environment DB is cached, "
         "so you can use this flag to remove existing DB before tests and create new one.",
)
@click.argument("test_options", nargs=-1, type=click.UNPROCESSED)
def test(**kwargs):
    TestCommand(**kwargs).run()


@cli.command(help=FixCodeStyle.__doc__)
@apply_common_options(initialized_repository_options)
@apply_common_options(devel_options)
def fix_code_style(**kwargs):
    FixCodeStyle(**kwargs).run()


@cli.command(help=BuildCommand.__doc__)
@apply_common_options(initialized_repository_options)
@apply_common_options(devel_options)
@click.option(
    "--image-context",
    help="Image context containing Dockerfile. Defaults to <project_dir>/docker",
)
def build(**kwargs):
    BuildCommand(**kwargs).run()


@cli.command(help=UpdateRequirementsCommand.__doc__)
@apply_common_options(initialized_repository_options)
@apply_common_options(devel_options)
@click.option(
    "--before3.6.0-5",
    "use_legacy_pip",
    is_flag=True,
    help="Add this flag to use update for an older python application.",
)
def update_requirements(**kwargs):
    UpdateRequirementsCommand(**kwargs).run()


@cli.command(help=PushCommand.__doc__)
@apply_common_options(initialized_repository_options)
@apply_common_options(devel_options)
def push(**kwargs):
    PushCommand(**kwargs).run()


@cli.command(help=DeployCommand.__doc__)
@apply_common_options(initialized_repository_options)
@apply_common_options(devel_options)
@click.option(
    "--build-url",
    help="URL to a CI/CD (eg. Jenkins) build. It will be used as a pod annotation.",
)
@click.option(
    "--aws-credentials",
    help="AWS key and secret. Required to deploy static files. Format: AWS_KEY:AWS_SECRET.",
)
@click.option(
    "--gcs-service-key-file",
    help="Service account key path for Google Cloud Storage. Required to deploy static files.",
)
@click.option(
    "--gcs-bucket-name",
    help="Google Cloud Storage bucket name. Required to deploy static files.",
)
def deploy(**kwargs):
    DeployCommand(**kwargs).run()


@cli.command(help=DebugCommand.__doc__)
@apply_common_options(initialized_repository_options)
def variables(**kwargs):
    DebugCommand(**kwargs).run()


@cli.command(help=JenkinsInfoCommand.__doc__)
@apply_common_options(initialized_repository_options)
def jenkins_info(**kwargs):
    JenkinsInfoCommand(**kwargs).run()


@cli.command(help=JenkinsInitCommand.__doc__)
@apply_common_options(initialized_repository_options)
def jenkins_init(**kwargs):
    JenkinsInitCommand(**kwargs).run()


@cli.command(help=JenkinsReconfigCommand.__doc__)
@apply_common_options(initialized_repository_options)
def jenkins_reconfig(**kwargs):
    JenkinsReconfigCommand(**kwargs).run()


@cli.command(help=JenkinsBuildCommand.__doc__)
@apply_common_options(initialized_repository_options)
def jenkins_build(**kwargs):
    JenkinsBuildCommand(**kwargs).run()


@cli.command(help=InstallCompletion.__doc__)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Force reinstall bash completion.",
)
def install_bash_completion(**kwargs):
    InstallCompletion(**kwargs).run()


@cli.command(help=InstallGlobalSecretsCommand.__doc__)
def install_global_secrets():
    InstallGlobalSecretsCommand().run()


@cli.command(help=SetupCommand.__doc__)
@click.option(
    "--development",
    "mode",
    flag_value="development",
    help="Sets development context using minikube. Development context uses secrets from repository.",
)
@click.option(
    "--production",
    "mode",
    flag_value="production",
)
def setup(**kwargs):
    SetupCommand(**kwargs).run()


@cli.command(help=InitCommand.__doc__)
@click.option(
    "--directory",
    default=".",
    type=click.Path(exists=True, file_okay=False),
    help="Select project root directory.",
)
@click.option(
    "--ember",  # TODO: better name...
    "init_type",
    flag_value=EmberInitType,
    default=PythonPackageInitType,
    help="Select ember template.",
)
def init(**kwargs):
    InitCommand(**kwargs).run()


if __name__ == "__main__":
    try:
        cli()
    except Exception as e:
        logger.error(e)
        logger.debug('', exc_info=True)
        exit(1)
    else:
        logger.info("Done")
