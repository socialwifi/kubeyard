import collections
import contextlib
import os
import pathlib
import shutil

import jinja2

templates_directory = pathlib.Path(__file__).parent / 'templates'
jinja_loader = jinja2.FileSystemLoader('/')
jinja_environment = jinja2.Environment(loader=jinja_loader)


def copy_template(template, destination, context=None):
    context = context or {}
    source = templates_directory / template
    environment = CopyEnvironment(source, destination, context)
    for path in traverse(source):
        if path.is_dir():
            DirectoryTemplate(path, environment).render()
        else:
            if path.match('*.template'):
                file_template = TemplateFileTemplate(path, environment)
            else:
                file_template = SimpleFileTemplate(path, environment)
            if file_template.destination.exists():
                print('file {} already exists. Skipping.'.format(str(file_template.destination)))
            else:
                file_template.render()


def recursive_chown(directory, uid):
    for path in traverse(directory):
        os.chown(str(path), uid=uid, gid=-1)


def traverse(path : pathlib.Path):
    yield path
    if path.is_dir():
        for sub in path.iterdir():
            yield from traverse(sub)

CopyEnvironment = collections.namedtuple('CopyEnvironment', ['source_root', 'destination_root', 'context'])


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


class SimpleFileTemplate(BaseTemplate):
    def render(self):
        shutil.copy(str(self.source), str(self.destination))


class TemplateFileTemplate(BaseTemplate):
    def render(self):
        template = jinja_environment.get_template(str(self.source))
        rendered = template.render(self.environment.context)
        with self.destination.open('w') as destination_file:
            destination_file.write(rendered)

    @property
    def destination(self):
        return super().destination.with_suffix('')
