import pathlib

from setuptools import find_packages
from setuptools import setup


def templates():
    for path in pathlib.Path('kubeyard/templates').glob('**/*'):
        if not path.is_dir():
            yield str(path.relative_to('kubeyard'))


def parse_requirements(filename, *args, **kwargs):
    """ load requirements from a pip requirements file """
    lineiter = (line.strip() for line in open(filename))
    return [line for line in lineiter if line and not line.startswith("#")]


setup(
    name='Kubeyard',
    version='docker',
    packages=find_packages(exclude=['tests']),
    install_requires=[str(r) for r in parse_requirements('base_requirements.txt', session=False)],
    test_suite='tests',
    entry_points={
        'console_scripts': [
            'kubeyard = kubeyard.entrypoints.kubeyard:cli_with_custom_commands',
            'sw-cli = kubeyard.entrypoints.kubeyard:cli_with_custom_commands',  # TODO: remove legacy
        ],
    },
    package_dir={'kubeyard': 'kubeyard'},
    package_data={'kubeyard': list(templates())},
    include_package_data=True,
)
