from optparse import OptionParser
import os
import pathlib

import sw_cli.files_generator


def run():
    print("initialising repo")
    options, args = parse_arguments()
    project_dst = pathlib.Path(options.directory)
    context = get_context()
    sw_cli.files_generator.copy_template('new_repository', project_dst, context=context)
    uid = int(os.environ['HOST_UID'])
    sw_cli.files_generator.recursive_chown(project_dst, uid)
    print('done')


def parse_arguments():
    parser = OptionParser()
    parser.add_option("--directory", dest="directory", default=".", help="Select project root directory.")
    return parser.parse_args()


def get_context():
    return dict(
        image_name=input('image name: '),
        service_name=input('service name: '),
        service_port=input('service port: '),
    )
