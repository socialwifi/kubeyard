kubeyard
========

|Latest Version| |Supported Python versions| |Wheel Status| |License|

A utility to develop, test and deploy Kubernetes microservices.

Requirements
------------

-  bash
-  minikube == v0.25.2
-  kubectl == 1.9.4
-  docker
-  git

   -  initialized repository with configured remote origin

Installation
------------

.. code:: bash

   rm -rf $HOME/kubeyard-venv
   virtualenv -p python3 $HOME/kubeyard-venv
   . $HOME/kubeyard-venv/bin/activate
   pip install kubeyard
   echo '. $HOME/kubeyard-venv/bin/activate' >> $HOME/.bashrc

.. |Latest Version| image:: https://img.shields.io/pypi/v/kubeyard.svg
   :target: https://pypi.python.org/pypi/kubeyard/
.. |Supported Python versions| image:: https://img.shields.io/pypi/pyversions/kubeyard.svg
   :target: https://pypi.python.org/pypi/kubeyard/
.. |Wheel Status| image:: https://img.shields.io/pypi/wheel/kubeyard.svg
   :target: https://pypi.python.org/pypi/kubeyard/
.. |License| image:: https://img.shields.io/pypi/l/kubeyard.svg
   :target: https://github.com/socialwifi/kubeyard/blob/master/LICENSE
