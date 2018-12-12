#!/bin/bash
cd $(pushd "$(dirname "${BASH_SOURCE[0]}")" > /dev/null; git rev-parse --show-toplevel; popd > /dev/null)
rm -rf $HOME/kubeyard-venv
virtualenv -p python3 $HOME/kubeyard-venv
. $HOME/kubeyard-venv/bin/activate
pip install --no-cache-dir .
echo '. $HOME/kubeyard-venv/bin/activate' >> $HOME/.bash.rc
