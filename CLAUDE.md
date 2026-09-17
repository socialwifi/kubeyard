# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# kubeyard

`kubeyard` is a command-line tool for developing, testing and deploying
Kubernetes microservices. It builds Docker images, runs tests against
throwaway databases, provisions development dependencies (Postgres, RabbitMQ,
Redis, …) into a cluster, and deploys a project's committed YAML through
`kubepy`.

It is a standalone, public package on PyPI and must stay usable by anyone.

## This is a public open-source project

**Never put Social WiFi–specific names, domains, service names, or internal
terminology into this repository.** That includes test fixtures and
documentation examples: names like microservice names or
internal hostnames are not allowed. Use generic names — `web`, `api`,
`migrate`, `chosen-namespace`, `example.test`.

The existing `socialwifi` references in `README.md` and `setup.py` are the
project's own GitHub URL and maintainer address; those are fine and stay.

## Core Technologies

- **Language:** Python 3.10–3.14 (see `setup.py` classifiers and `tox.ini`). Do
  not use syntax newer than 3.10.
- **CLI:** `click`, with commands registered in `kubeyard/entrypoints/kubeyard.py`.
  Executables in a project's `scripts/` directory are also exposed as
  subcommands by `CustomCommandsLoader`.
- **Subprocesses:** the `sh` library, pinned `<2`. Keep the existing call style
  (`sh.kubectl(...)`, `sh.kubectl.get.pods(...)`).
- **Kubernetes:** `kubepy` does the applying. Local source lives at `../kubepy`.
- **Config:** a project's `config/kubeyard.yml`, layered over
  `~/.kubeyard/context.yml` and defaults in `kubeyard/settings.py`, assembled by
  `kubeyard/context_factories.py`. Every context key is exported as an
  environment variable to custom scripts and to Docker.

## Project Structure

- `kubeyard/context_factories.py` — builds the context every command reads.
- `kubeyard/base_command.py` — `InitialisedRepositoryCommand`, the base for
  anything that needs a project directory.
- `kubeyard/commands/devel.py` — `BaseDevelCommand`: image naming, tags, volumes,
  and the custom-script override mechanism every dev command inherits.
- `kubeyard/commands/` — one module per command (`build`, `test`, `deploy`,
  `shell`, …). A project can override any of them with an executable of the same
  name in its `scripts/` directory.
- `kubeyard/kubernetes.py` — secrets and the global ConfigMap.
- `kubeyard/dependencies.py`, `kubeyard/commands/dev_requirements.py` — the
  development dependencies a project declares in `dev_requirements`.
- `kubeyard/minikube.py` — cluster lifecycle. Note `--mount-string $HOME:$HOME`:
  **project directories must live under `$HOME` or host volumes silently fail to
  mount.**
- `kubeyard/templates/` — Jinja templates used by `kubeyard init`. They are
  rendered **once**, at init; the rendered result is what each project commits.
  Changing a template does not change already-scaffolded projects.

## Development

```bash
tox run -e lint,py     # linters plus tests on the current interpreter
pytest tests/ -q       # tests only
```

`tox -e py` uses whichever interpreter is active; CI runs the full 3.10–3.14
matrix on push.

Prefer extracting pure functions over data and testing those. Anything that
shells out to `kubectl`, `docker` or `minikube` needs a cluster, so keep the
decision logic separable from the invocation.

## Style Conventions

Linting is `flake8` and `isort`, configured in `setup.cfg`.

- PEP8, max line length **120**.
- Trailing commas in multi-line literals and calls.
- Import whole modules, not individual names: `from kubeyard import kubernetes`
  then `kubernetes.install_secrets(...)`. `isort` uses `force_single_line`, so
  one import per line.
- Write clean, self-documenting code: short high-level functions calling
  well-named low-level ones, rather than long functions with comments explaining
  each step.

## Backward Compatibility

This is a published tool used against real clusters. New behaviour is opt-in: a
command run without the new flag, file or environment variable must behave
exactly as it did before. When adding an optional `kubectl` argument, emit
nothing at all when it is unset rather than emitting a default — passing an
explicit default overrides whatever the user configured in their kubectl
context.

## Commits

- **Group by logical change, not by step.** An option and the code that uses it
  are one commit, not two. Do not produce a long series of small commits.
- **When fixing something on this branch, amend the commit that introduced it**
  rather than appending a follow-up commit.
- Subject line, then a **blank line**, then any trailers. Writing a trailer
  directly under the subject folds it into the subject line.
- Do not push, tag, or upload to PyPI without being asked.
