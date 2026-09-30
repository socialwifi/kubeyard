---
name: workspaces
description: Use when starting a feature or ticket in a repository managed by kubeyard (it has config/kubeyard.yml), when work needs an isolated development environment, when it spans several such repositories, or when several agents work in parallel. Covers isolated workspaces instead of bare git worktrees.
---

# kubeyard workspaces

A repository is kubeyard-managed if it has `config/kubeyard.yml`. Everything
below applies only inside one.

## Use a workspace, not a bare worktree

**Do not run `git worktree add` to start feature work here.** A worktree gives
you an isolated *checkout* but leaves you sharing one cluster namespace, one
database and one message broker with every other checkout, so two pieces of
work overwrite each other's Deployments and steal each other's queue jobs.

Use a workspace instead. It creates the worktree *and* the isolation:

```bash
kubeyard workspace create <name>
cd "$(kubeyard workspace create <name> --print-path)"
```

`create` is idempotent, so the second call reuses what the first made and just
prints the path. From the main checkout it creates `.worktrees/<name>` on
branch `ws-<name>`, creates the namespace `ws-<name>` with its own database and
broker, and points every service you have *not* deployed there back at the
shared namespace. Run inside an existing worktree it attaches that one instead
of nesting another, and the name defaults to the branch.

A name is required in the main checkout: the branch there names the shared
environment, not a workspace.

Add `.worktrees/` to the repository's `.gitignore` if it is not there already,
or git will offer to commit the worktree into the branch it was made from.
`create` warns when this is missing.

## Work spanning several repositories

Run `kubeyard workspace create` **once per repository, with the same name**.
The namespace is `ws-<name>` regardless of which repository you run it from, so
the same name puts them all in one environment. Different names give you
several unrelated environments, which is usually a bug rather than a plan.

Do this in the orchestrating session *before* dispatching agents, and hand each
agent its worktree path. Agents that each run `create` concurrently race on
creating the same namespace.

## What to deploy into it

Deploy only what you are changing. Everything else is aliased back to the
shared namespace and keeps working.

Some services must not be workspaced at all. Two kinds come up:

- **Cluster singletons**, such as an ingress whose Service claims fixed node
  ports. Node ports are cluster-wide rather than per-namespace, so a second copy
  fails to create its Service. These usually need no workspace anyway: an ingress
  that derives the namespace from the hostname already routes into yours. A
  change to one lands on the shared instance and affects everyone.
- **Services holding state every other service validates against**, such as one
  issuing opaque tokens that others verify by calling back to it. A workspaced
  copy starts with an empty database, so it rejects what the shared services
  accept and they reject what it issues.

Read the service's own `CLAUDE.md` and `scripts/deploy` before deploying it into
a workspace: one that should stay shared usually says so, and may refuse or warn
interactively.

## Finishing

`kubeyard workspace destroy` removes the namespace, its hosts entries and its
data. The worktree and branch are git's, and are left alone.

## When a bare worktree is still right

Throwaway worktrees for history rewriting are fine and are not workspace work:

```bash
git worktree add --detach <path> <commit>
```

That is the supported way to rebase or amend in a repository with uncommitted
changes, without touching the working copy. It needs no namespace.

## More

`references/workspace-model.md` has the alias overlay, the full command table,
hostnames and TLS, and what to check when a workspace misbehaves.

For building, testing, deploying and configuring the project, see the
`kubeyard:usage` skill.
