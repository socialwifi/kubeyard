#!/bin/bash

rm -rf $HOME/sw-cli-venv
virtualenv -p python3 $HOME/sw-cli-venv
. $HOME/sw-cli-venv/bin/activate
python setup.py install
echo '. $HOME/sw-cli-venv/bin/activate' >> $HOME/.bash.rc
