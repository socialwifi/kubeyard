from pip.req import parse_requirements
from setuptools import find_packages
from setuptools import setup


setup(
    name='Sw-Cli',
    version='docker',
    packages=find_packages(exclude=['tests']),
    install_requires=[str(ir.req) for ir in parse_requirements('base_requirements.txt', session=False)],
    test_suite='tests',
    entry_points={
        'console_scripts': [
            'sw-cli = sw_cli.entrypoints.sw_cli:run',
        ],
    },
)
