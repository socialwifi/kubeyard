---
name: usage
description: Use when building, testing, deploying, configuring or debugging a project managed by kubeyard (it has config/kubeyard.yml) - what a command does, which flag to pass, where a setting comes from, why a change to a manifest or a config file did not take effect.
---

# Using kubeyard in a project

`kubeyard` builds, tests and deploys Kubernetes microservices. A repository is
kubeyard-managed if it has `config/kubeyard.yml`.

**The repository's own `CLAUDE.md` is more specific than this skill** for how to
build, test and deploy *that* service: which migration tool it uses, what its
seed command does, what its `scripts/` overrides change. Read it first and treat
this as the tool-level reference behind it.

## Commands

| | |
|---|---|
| `build` | Builds the image used by `test` and `deploy`. |
| `test` | Runs the test suite in that image. |
| `deploy` | Applies the project's Kubernetes definitions. |
| `shell` | Execs into the container. Also takes a command on stdin. |
| `seed` | Runs the project's `dev_seed_command`. |
| `push` | `docker push` for the built image. |
| `undeploy` | Removes the project's Kubernetes objects. |
| `variables` | Prints the assembled context. |
| `workspace` | Isolated development environments. See the `kubeyard:workspaces` skill. |
| `setup` | One-off machine setup, development or production. |
| `init` | Scaffolds a new repository. |
| `fix-code-style`, `update-requirements`, `install-global-secrets`, `install-bash-completion` | As named. |

`kubeyard --help` and `kubeyard <command> --help` are authoritative, and are
worth checking when something here does not match what the installed version
does.

`shell` also takes a command on stdin, as in
`echo "check_code_style" | kubeyard shell`. **This works non-interactively**,
which is where agents run. `kubectl exec` prints

```
Unable to use a TTY - input is not a terminal or the right kind of file
```

and then runs the command anyway, with stdin still forwarded. That line is a
warning, not a failure, and is not a reason to retry or to fall back to
something else.

When the command itself exits non-zero, kubeyard surfaces it as a Python
traceback ending in `sh.ErrorReturnCode_N`. The real error is in the output
*above* the traceback; the traceback only reports that the container exited
non-zero.

## Custom scripts override built-ins

An executable in the repository's `scripts/` directory shadows the kubeyard
command of the same name. `kubeyard <command> --default` runs the built-in one,
which is how those scripts delegate after doing their own work.

A script is given the command line its command was invoked with, so hand it back
when delegating, or the built-in runs as if nothing had been passed:

```bash
exec kubeyard deploy --default "$@"
```

`scripts/test` is the exception: its arguments are the test runner's, because
that is what `kubeyard test -k my_test` means. Runner arguments that clash with a
kubeyard option go after `--`, which is the only way to reach the runner with
`-v` or `--tag`:

```bash
kubeyard test --tag 61 -- -v -k my_test
```

Scripts receive the whole context as environment variables, including
`KUBEYARD_MODE` (`development` or `production`), `KUBEYARD_NAMESPACE`,
`KUBEYARD_WORKSPACE` and `PROJECT_DIR`. A script that should only act in
development guards on `KUBEYARD_MODE`; one that should only act inside a
workspace also checks `KUBEYARD_WORKSPACE`.

Before writing a wrapper around a kubeyard command, check whether
`scripts/<command>` already exists. Your change probably belongs there.

## Configuration

Three layers, each overriding the previous:

1. kubeyard's built-in defaults
2. the project's `config/kubeyard.yml`
3. `~/.kubeyard/context.yml`

The user file wins, but for keys kubeyard defines the order rarely matters,
because each one belongs to exactly one layer and putting it in the wrong file is
an error:

- `base_domain` is machine-wide, so only `~/.kubeyard/context.yml` may set it. It
  is the domain this environment serves, it reaches every container as
  `BASE_DOMAIN`, and one `global` ConfigMap serves the whole namespace, so no
  single project can own it. It has no default; `kubeyard setup` asks for it.
- everything else describes a project, so only `config/kubeyard.yml` may set it.

Keys kubeyard does not define are unconstrained and can go in either file.
`kubeyard variables` prints the assembled result.

Every context key is also exported as an environment variable to custom scripts
and into the container.

## Constraints that bite

- **Project directories must live under `$HOME`.** That is the only path the
  cluster VM mounts. Anywhere else, host volumes silently fail to mount and the
  container runs stale code, with no error to tell you.
- **The development test database is cached between runs.** After adding a
  migration, one run needs `kubeyard test --force-migrate-db`. To drop the
  database and start again, `--force-recreate-db`. Without either, the suite
  runs against the old schema and fails in ways that look like application bugs.

## Manifests

`references/manifests.md` covers `deploy/` versus `development_overrides/`, how
the two are merged, and the merge trap that produces a manifest the Kubernetes
API rejects.
