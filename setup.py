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


def get_long_description():
    with open('README.md') as readme_file:
        return readme_file.read()

setup(
    name='kubeyard',
    version='0.2.2',
    description='A utility to develop, test and deploy Kubernetes microservices.',
    long_description=get_long_description(),
    long_description_content_type='text/markdown',
    author='Social WiFi',
    author_email='it@socialwifi.com',
    url='https://github.com/socialwifi/kubeyard',
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
    license='BSD',
    classifiers=[
        'Environment :: Console',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
    ]
)
