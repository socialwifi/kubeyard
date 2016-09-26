import contextlib
import pathlib
import shutil

import collections

templates_directory = pathlib.Path(__file__).parent / 'templates'


def copy_template(template, destination):
    source = templates_directory / template
    environment = CopyEnvironment(source, destination)
    for path in traverse(source):
        if path.is_dir():
            DirectoryTemplate(path, environment).render()
        else:
            file_template = FileTemplate(path, environment)
            if file_template.destination.exists():
                print('file {} already exists. Skipping.'.format(str(file_template.destination)))
            else:
                file_template.render()



def traverse(path : pathlib.Path):
    yield path
    if path.is_dir():
        for sub in path.iterdir():
            yield from traverse(sub)

CopyEnvironment = collections.namedtuple('CopyEnvironment', ['source_root', 'destination_root'])


class BaseTemplate:
    def __init__(self, source, environment):
        self.source = source
        self.environment = environment

    @property
    def destination(self):
        relative_path = self.source.relative_to(self.environment.source_root)
        return self.environment.destination_root / relative_path

    def render(self):
        raise NotImplementedError


class DirectoryTemplate(BaseTemplate):
    def render(self):
        with contextlib.suppress(FileExistsError):
            self.destination.mkdir()


class FileTemplate(BaseTemplate):
    def render(self):
        shutil.copy(str(self.source), str(self.destination))
