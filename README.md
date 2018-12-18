# kubeyard
[![Latest Version](https://img.shields.io/pypi/v/kubeyard.svg)](https://pypi.python.org/pypi/kubeyard/)
[![Supported Python versions](https://img.shields.io/pypi/pyversions/kubeyard.svg)](https://pypi.python.org/pypi/kubeyard/)
[![Wheel Status](https://img.shields.io/pypi/wheel/kubeyard.svg)](https://pypi.python.org/pypi/kubeyard/)
[![License](https://img.shields.io/pypi/l/kubeyard.svg)](https://github.com/socialwifi/kubeyard/blob/master/LICENSE)
[![Build](https://img.shields.io/circleci/project/github/socialwifi/kubeyard/master.svg)](https://circleci.com/gh/socialwifi/kubeyard)


A utility to develop, test and deploy Kubernetes microservices.

## Requirements

- bash
- minikube == v0.25.2
- kubectl == 1.9.4
- docker
- git
    - initialized repository with configured remote origin

## Installation

```bash
rm -rf $HOME/kubeyard-venv
virtualenv -p python3 $HOME/kubeyard-venv
. $HOME/kubeyard-venv/bin/activate
pip install kubeyard
echo '. $HOME/kubeyard-venv/bin/activate' >> $HOME/.bashrc
```
