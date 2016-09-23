#!/usr/bin/env python

import pathlib
import sw_cli.flies_generator

def run():
    print("installing sw-cli")
    sw_cli_dst = pathlib.Path('/hostfs/etc/bash_completion.d/sw-cli')
    sw_cli.flies_generator.copy_template('sw-cli-completion.sh', sw_cli_dst)
    sw_cli_dst.chmod(0o644)
    print('done')

if __name__ == '__main__':
    run()
