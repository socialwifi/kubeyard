import pathlib
import sw_cli.files_generator

def run():
    print("installing sw-cli")
    sw_cli_dst = pathlib.Path('/etc/bash_completion.d/sw-cli')
    sw_cli.files_generator.copy_template('sw-cli-completion.sh', sw_cli_dst)
    sw_cli_dst.chmod(0o644)
    print('done')
