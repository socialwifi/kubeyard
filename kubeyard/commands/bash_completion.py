import logging
import pathlib
import tempfile

import sh

import kubeyard.files_generator

from kubeyard import base_command

logger = logging.getLogger(__name__)


class InstallCompletion(base_command.BaseCommand):
    """
    Run this to enable bash completion. It writes /etc/bash_completion.d/kubeyard file.
    It will work automatically on your next bash use.

    You can enable it in your current sessions by running `. /etc/bash_completion.d/kubeyard`
    """
    completion_dst = pathlib.Path('/etc/bash_completion.d/kubeyard')

    def __init__(self, *, force):
        self.force = force

    def run(self):
        logger.info("Installing kubeyard completion...")
        if self.completion_dst.exists() and not self.force:
            logger.warning('File {} already exists. Skipping.'.format(str(self.completion_dst)))
        else:
            with tempfile.NamedTemporaryFile(mode='r') as f:
                completion_dst_tmp = pathlib.Path(f.name)
                kubeyard.files_generator.copy_template('kubeyard-completion.sh', completion_dst_tmp, replace=True)
                completion_dst_tmp.chmod(0o644)
                with sh.contrib.sudo(_with=True):
                    sh.cp(str(completion_dst_tmp), str(self.completion_dst))
