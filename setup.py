import pathlib

from setuptools import find_packages
from setuptools import setup


def templates():
    for path in pathlib.Path('sw_cli/templates').glob('**/*'):
        if not path.is_dir():
            yield str(path.relative_to('sw_cli'))


def parse_requirements(filename, *args, **kwargs):
    """ load requirements from a pip requirements file """
    lineiter = (line.strip() for line in open(filename))
    return [line for line in lineiter if line and not line.startswith("#")]


setup(
    name='Sw-Cli',
    version='docker',
    packages=find_packages(exclude=['tests']),
    install_requires=[str(r) for r in parse_requirements('base_requirements.txt', session=False)],
    test_suite='tests',
    entry_points={
        'console_scripts': [
            'sw-cli = sw_cli.entrypoints.sw_cli:cli',
            'sw-cli-old = sw_cli.entrypoints.sw_cli_old:run',
        ],
    },
    package_dir={'sw_cli': 'sw_cli'},
    package_data={'sw_cli': list(templates())},
    include_package_data=True,
)
