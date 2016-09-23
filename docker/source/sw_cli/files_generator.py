import contextlib
import pathlib
import shutil

templates_directory = pathlib.Path(__file__).parent / 'templates'


def copy_template(template, destination):
    source = templates_directory / template
    for path in traverse(source):
        path_destination = destination / path.relative_to(source)
        if path.is_dir():
            with contextlib.suppress(FileExistsError):
                path_destination.mkdir()
        else:
            if path_destination.exists():
                print('file {} already exists. Skipping.'.format(str(path_destination)))
            else:
                shutil.copy(str(path), str(path_destination))


def traverse(path : pathlib.Path):
    yield path
    if path.is_dir():
        for sub in path.iterdir():
            yield from traverse(sub)
