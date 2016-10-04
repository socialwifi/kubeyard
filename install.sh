#!/bin/bash
cd $(pushd "$(dirname "${BASH_SOURCE[0]}")" > /dev/null; git rev-parse --show-toplevel; popd > /dev/null)
rm -rf $HOME/sw-cli-venv
virtualenv -p python3 $HOME/sw-cli-venv
. $HOME/sw-cli-venv/bin/activate
pip install --no-cache-dir .
echo '. $HOME/sw-cli-venv/bin/activate' >> $HOME/.bash.rc
