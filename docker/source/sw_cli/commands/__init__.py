from collections import namedtuple

from . import bash_completion
from . import install_bash_completion
from . import init_repo

CommandDeclaration = namedtuple('CommandDeclaration', ['name', 'source'])

commands = [
    CommandDeclaration('init_repo', init_repo.run),
    CommandDeclaration('install_bash_completion', install_bash_completion.run),
    CommandDeclaration('bash_completion', bash_completion.run),
]
