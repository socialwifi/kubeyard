from pip.req import parse_requirements
from setuptools import find_packages
from setuptools import setup


setup(
    name='Application_name',
    version='docker',
    packages=find_packages(exclude=['tests']),
    install_requires=[str(ir.req) for ir in parse_requirements('base_requirements.txt', session=False)],
    test_suite='tests',
)
