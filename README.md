# kubeyard
[![Latest Version](https://img.shields.io/pypi/v/kubeyard.svg)](https://pypi.python.org/pypi/kubeyard/)
[![Supported Python versions](https://img.shields.io/pypi/pyversions/kubeyard.svg)](https://pypi.python.org/pypi/kubeyard/)
[![Wheel Status](https://img.shields.io/pypi/wheel/kubeyard.svg)](https://pypi.python.org/pypi/kubeyard/)
[![License](https://img.shields.io/pypi/l/kubeyard.svg)](https://github.com/socialwifi/kubeyard/blob/master/LICENSE)
[![Build](https://img.shields.io/circleci/project/github/socialwifi/kubeyard/master.svg)](https://circleci.com/gh/socialwifi/kubeyard)


A utility to develop, test and deploy Kubernetes microservices.

## Requirements

- bash
- minikube
- kubectl
- docker
- conntrack

**Important:** Kubeyard is tested on:

- minikube == v1.29.0 (should work with v1.29.0 and above)
- docker == 20.10.23 (should work with any version)
- kubectl == v1.21.14 (should work with v1.21.14 and above)

## Installation

```bash
rm -rf $HOME/kubeyard-venv
virtualenv -p python3 $HOME/kubeyard-venv
. $HOME/kubeyard-venv/bin/activate
pip install kubeyard
echo '. $HOME/kubeyard-venv/bin/activate' >> $HOME/.bashrc
```

## Configuration

Settings come from three layers, each overriding the one before:

1. defaults built into kubeyard
2. the project's `config/kubeyard.yml`
3. your `~/.kubeyard/context.yml`

Your own file wins over everything, so keep it to machine-wide settings such as
`KUBEYARD_MODE` or `KUBEYARD_VM_DRIVER`. A project-level key placed there applies
to every project on the machine, and no project can override it: if one of them
needs a different value, it has no way to ask for one.

Every context key is exported as an environment variable to custom scripts and
to Docker builds.

## Workspaces

A workspace is an isolated development environment: one Kubernetes namespace
(`ws-<name>`) holding the services you are changing, with every other service
aliased back to `default`. This lets several coding agents, or several features
in flight, run concurrently in separate git worktrees without colliding.

    kubeyard workspace create example
    cd .worktrees/example
    kubeyard build && kubeyard deploy

`create` makes the git worktree too, on a branch `ws-<name>`, and prints the
path to `cd` into, along with how to tear it down again.

The workspace is recorded in a `.kubeyard-workspace` file in the worktree, so
every later command picks it up automatically. Add both that filename and
`.worktrees/` to the repository's `.gitignore`.

    kubeyard workspace show       # what is deployed here versus aliased
    kubeyard undeploy             # put this service back on the shared instance
    kubeyard workspace destroy    # remove the whole workspace

### Seeding development data

A project can declare how to load its development data:

```yaml
dev_seed_command: python -m tests.demo
dev_seed_pod: api            # optional; defaults to the shortest running pod name
```

`kubeyard seed` then runs that command inside the deployed pod, in the namespace
kubeyard already knows - so from a workspace it seeds that workspace's database.

`deploy` runs it for you when it has just created the database - so a new workspace,
or a new checkout of the shared environment, comes up with data already in it. A
redeploy finds the database present and leaves it alone.

Without a `.kubeyard-workspace` file, kubeyard behaves exactly as it always has
and targets the shared environment.

See [docs/workspaces.md](docs/workspaces.md) for why workspaces exist, how the
alias overlay works, and the limits worth knowing before relying on them.
