# Workspaces in detail

## What a workspace is

A Kubernetes namespace `ws-<name>`, a git worktree attached to it, and an alias
overlay. Services you deploy into it are real; every service you have not
deployed is an `ExternalName` Service pointing back at the shared namespace. So
hardcoded inter-service addresses such as `http://other-service/internal/`
resolve without any change to application code.

The workspace gets its own database and message broker, so data and queues are
fully separated from the shared environment and from other workspaces.

## Commands

| Command | What it does |
|---|---|
| `workspace create <name>` | Creates the namespace, worktree and domains. Idempotent. `--print-path` prints only the worktree path. `--worktree-root` / `KUBEYARD_WORKTREE_ROOT` change where worktrees go (default `.worktrees`, relative to the repository). |
| `workspace show` | The active workspace, and which services are real rather than aliased. Run this first when something behaves unexpectedly. |
| `workspace list` | Every workspace namespace in the cluster. |
| `workspace sync` | Reconciles the alias overlay against what is currently deployed. Run it after deploying or undeploying a service, if `show` disagrees with reality. |
| `workspace destroy` | Deletes the namespace, its hosts entries and its data. Leaves the git worktree and branch alone. |

Commands other than `create` infer the workspace from the directory you run
them in, or take the name explicitly.

## Hostnames

Services in a workspace are reachable at `<service>.<workspace>.ws.<tld>`,
nested rather than flattened, because a TLS wildcard matches exactly one label
and browsers reject `*.*.example.com`. Certificates come from a locally trusted
development CA, which has to be installed in the system trust store and in each
browser profile with its own certificate database.

If a hostname resolves but the certificate is rejected, the CA is not installed
for *that* browser profile. Browsers keep per-profile certificate databases, so
installing it once system-wide is not always enough.

## Deciding what to deploy into a workspace

Deploy the services you are changing. Leave everything else aliased.

Be careful with services that hold state other services validate against, for
example a service that issues opaque tokens which every other service verifies
by calling back to it. Deploying such a service into a workspace gives it an
empty database, so tokens it issues are rejected by every service still running
in the shared namespace, and tokens from the shared one are rejected by it. The
symptom is confusing: you can log in, then every subsequent API call fails
authorization.

Leave those aliased to the shared namespace unless you are changing them, and
if you must workspace one, workspace everything that talks to it, each with its
own seeded data.

A repository that should normally stay shared usually says so in its
`CLAUDE.md`, and may have a `scripts/deploy` that warns and asks for
confirmation. Read the warning rather than dismissing it.

## Troubleshooting

- **A service returns data you did not expect**: `workspace show`. It is
  probably aliased to the shared namespace and you are reading shared data.
- **Code changes have no effect**: the checkout is outside `$HOME`, so the host
  volume did not mount. Move it under `$HOME`.
- **Deployed a service but other services still reach the shared one**:
  `workspace sync`.
- **Two workspaces interfering**: check you used the same name deliberately.
  The namespace is derived from the name, not from the directory.
