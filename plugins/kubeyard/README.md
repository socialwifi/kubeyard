# kubeyard plugin for Claude Code

Teaches Claude Code to use kubeyard workspaces instead of bare git worktrees
when starting work in a kubeyard-managed repository, and gives it the command
surface and the constraints that are easy to get wrong.

## Install

```
/plugin marketplace add socialwifi/kubeyard
/plugin install kubeyard@kubeyard
```

Or, while developing it, load it straight from a checkout:

```
claude --plugin-dir plugins/kubeyard
```

## What it adds

- **`kubeyard:workspaces`**, a skill for starting work: use a workspace rather
  than a bare `git worktree add`, run one workspace across several repositories,
  and what not to deploy into one.

- **`kubeyard:usage`**, a skill for using the tool: the command surface, the
  `scripts/` override mechanism, configuration precedence, and `deploy/` versus
  `development_overrides/`. This is the canonical place those are documented, so
  a project's own `CLAUDE.md` can cover only what is specific to that service
  rather than restating the tool.

Each skill keeps its depth in `references/`, loaded only when needed.

- **A `PreToolUse` hook** on `git worktree add`. In a kubeyard project a bare
  worktree gives an isolated checkout but leaves you sharing one namespace,
  database and broker with every other checkout, so two pieces of work overwrite
  each other's Deployments and steal each other's queue jobs. The hook points at
  `kubeyard workspace create` instead.

  `git worktree add --detach` passes silently. That is the supported way to
  rebase or amend in a repository with uncommitted changes, and it needs no
  namespace.

  The hook requires `jq`.

## Make the hook block instead of warn

By default it warns: Claude sees the message and decides. To refuse the command
outright, edit `hooks/kubeyard-worktree-guard.sh` and replace the
`additionalContext` line in the final `jq` call with:

```
permissionDecision: "deny",
permissionDecisionReason: $message
```

Blocking is what reliably changes behaviour, at the cost of occasionally
refusing a legitimate worktree the `--detach` rule does not cover.

## Project-specific rules

The skill is deliberately generic. Anything true only of your services, such as
a service that must never be workspaced because every other service validates
state against it, belongs in that repository's own `CLAUDE.md` and in its
`scripts/deploy`, not here.
