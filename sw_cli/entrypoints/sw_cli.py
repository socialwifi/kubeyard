#!/usr/bin/env python
import click

from sw_cli import settings
from sw_cli.commands.test import TestCommand


@click.group()
def cli():
    """
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
@click.argument('test_options', nargs=-1, type=click.UNPROCESSED)
def test(**kwargs):
    TestCommand(**kwargs).run()


if __name__ == "__main__":
    cli()
