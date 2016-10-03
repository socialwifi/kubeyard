from collections import namedtuple

from . import bash_completion
from . import install_bash_completion
from . import init_repo
from . import jenkins
from . import debug

CommandDeclaration = namedtuple('CommandDeclaration', ['name', 'source'])

commands = [
    CommandDeclaration('init_repo', init_repo.run),
    CommandDeclaration('install_bash_completion', install_bash_completion.run),
    CommandDeclaration('bash_completion', bash_completion.run),
    CommandDeclaration('jenkins_init', jenkins.init),
    CommandDeclaration('jenkins_build', jenkins.build),
    CommandDeclaration('jenkins_reconfig', jenkins.reconfig),
    CommandDeclaration('jenkins_info', jenkins.info),
    CommandDeclaration('variables', debug.variables)
]
