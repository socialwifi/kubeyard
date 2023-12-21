# Quickstart

We will setup a simple django app using kubeyard built-in template.

**IMPORTANT:** Kubeyard uses docker as "VM" driver, so many containers will be created on your host to create minikube cluster.

## Requirements:

- docker - [install guide](https://docs.docker.com/install/linux/docker-ce/ubuntu/) and [setup guide](https://docs.docker.com/install/linux/linux-postinstall/)
- minikube - [install guide](https://kubernetes.io/docs/tasks/tools/install-minikube/#linux)
- kubectl - [install guide](https://kubernetes.io/docs/tasks/tools/install-kubectl/#install-kubectl-binary-using-curl)

## Optional requirements:

- some kind of virtual environment for kubeyard (recommended)

## Setup guide

First, we need to setup kubeyard:

```bash
pip install kubeyard
kubeyard                            # you can see available commands
kubeyard install-bash-completion    # optional, gives you bash completion for kubeyard
kubeyard setup --development
kubeyard install-global-secrets
```

It may take about 10 minutes (or even more - it depends on your internet 
connection - minikube needs to download docker images for the k8s cluster)
to setup cluster. Next run will be significantly faster.

_If you have a problem with minikube setup, please check if all ports required are available (1-32767)._

Now, we are ready to setup project from the template!

```bash
mkdir simple_django
cd simple_django/
kubeyard init --template django 
```

Kubeyard will ask you about some project details. You can leave default values for now.
Now you can see the project structure:

- **config**
    - kubeyard.yml - project-level configuration file for kubeyard
    - kubernetes/
        - deploy/ - all definition files used to deploy application on cluster
        - development_overrides/ - files that overrides values from deploy/ directory. Used only in `development` mode
        - dev_secrets/ - development secrets files. Used only in `development` mode
- **docker** - all files that will be in docker image such as:
    - Dockerfile - dockerfile based on python package image (many `ON BUILD` automagic).
    - requirements/ - all (compiled) requirements. In our example only python requirements.
    - source - application sources
- **scripts** - empty directory, used to override or add project-specific commands to kubeyard (we don't do that in quickstart guide)


Ok, lets build project image:
```bash
kubeyard build
```
Kubeyard can automatically build images and add a tag. For the development environment, it will be `:dev`.

We can run test inside image:
```bash
kubeyard test
```

If everything is fine, we can do the most important part - application deployment.

```bash
kubeyard deploy
```

You will be asked for sudo password.
Kubeyard needs it to configure /etc/hosts and make your service accessible via domain.

Now your first application is deployed on k8s cluster! You can access it using
http://simple-django.testing
