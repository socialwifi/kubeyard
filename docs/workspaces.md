# Workspaces

A workspace lets you deploy the services you are changing into a namespace of
your own, while everything you are *not* changing keeps resolving to the shared
development cluster.

## Why

kubeyard deploys to a development cluster on your own machine, so the constraint
is not other developers - it is that the cluster holds one copy of each service,
and one deployment of a service is often not enough.

The case this was built for is agentic development. Several coding agents, each
in its own git worktree, each building, deploying and testing the service it is
changing. Sharing one deployment they overwrite each other's images, run
migrations against the same database, and collide on fixed container names
during tests. The work has to be serialised, which is exactly what running
agents in parallel was meant to avoid.

The same problem shows up without agents. Two features in flight with different
schema migrations means redeploying and re-seeding every time you switch
between them. A workspace each lets both stay up, and switching becomes `cd`.

Either way the bargain is the same: the services you are changing are yours
alone, and everything else is borrowed from the shared environment.

## The idea

Creating a workspace makes a namespace, `ws-<name>`, and fills it with
`ExternalName` Services pointing at `default` - one for every Service in the
shared namespace. Nothing is running in the workspace yet, but every name
already resolves.

```
namespace ws-alice

  api         -> ExternalName -> api.default.svc.cluster.local
  web         -> ExternalName -> web.default.svc.cluster.local
  mailer      -> ExternalName -> mailer.default.svc.cluster.local
```

Deploying a project into the workspace replaces its alias with the real thing:

```
namespace ws-alice

  api         -> ClusterIP, your pods, your database    <- deployed here
  web         -> ExternalName -> web.default.svc.cluster.local
  mailer      -> ExternalName -> mailer.default.svc.cluster.local
```

This is what makes the feature cheap. Code that calls `http://web/internal/`
needs no change and no configuration: inside the workspace that name resolves to
the shared `web`, until the day you deploy your own, at which point it resolves
to yours. Service discovery stays ordinary DNS.

## Using it

A workspace is tied to a directory, so the natural unit is a git worktree.
Keeping it inside the repository is deliberate: kubeyard requires the project
directory to live under `$HOME`, because that is all minikube mounts, and a
worktree under the repository inherits that for free.

```bash
git worktree add .workspaces/alice -b ws-alice
cd .workspaces/alice
kubeyard workspace create alice
kubeyard build && kubeyard deploy
```

Add `.workspaces/` to the repository's `.gitignore`, or git will offer to
commit the worktree into the branch it was made from.

`create` writes a `.kubeyard-workspace` file containing the name. Every later
kubeyard command run from that directory picks it up, so there is no flag to
remember and no way to deploy to the wrong place by forgetting one.

Add the marker to your global git ignore once, so it is never committed:

```bash
echo '.kubeyard-workspace' >> ~/.config/git/ignore
```

The rest of the commands:

```bash
kubeyard workspace show      # what is real here, what is aliased, what is missing
kubeyard workspace list      # every workspace in the cluster
kubeyard workspace sync      # re-align the aliases after services appear or retire
kubeyard undeploy            # put this one project back on the shared instance
kubeyard workspace destroy   # delete the namespace and this project's host entries
```

`KUBEYARD_WORKSPACE` overrides the marker file if you need to; setting it to the
empty string forces the shared environment for one command.

## How it works

**The marker.** `kubeyard/workspace.py` resolves the active workspace from
`KUBEYARD_WORKSPACE` first, then `.kubeyard-workspace`, then falls back to none.
Namespaces are named `ws-<workspace>` and carry the label
`kubeyard.io/workspace=<name>`, which is how `workspace list` finds them.

**Namespace threading.** Every `kubectl` invocation routes its namespace through
one helper, `kubectl.namespace_args`, which returns an empty tuple when no
workspace is active. Outside a workspace the command line is therefore
byte-identical to what it was before this feature existed, and still honours
whatever namespace your kubectl context selects.

**The alias overlay.** `kubeyard/aliases.py` reconciles three sets: the Services
in `default`, the real (non-alias) Services in the workspace, and the aliases
already there. Aliases carry the label `kubeyard.io/alias=true`, and only
labelled objects are ever deleted, so a real deployment cannot be removed by
alias housekeeping. Development requirements are excluded from aliasing
entirely - see below.

**Development requirements.** A workspace gets its own Postgres, RabbitMQ, Redis
and so on, rather than aliases to the shared ones. That is the point: an
isolated database is most of the value. Migrations and seeds therefore run
against your data, not the team's.

**Images and test containers.** In development the image tag becomes
`dev-<workspace>`, so concurrent builds and test runs in different workspaces
neither overwrite each other's images nor collide on container names.

**Host entries.** Projects that declare `dev_domains` get workspace-scoped
hostnames of the form `<domain>.<workspace>.ws.<dev_tld>`, written to
`/etc/hosts`. This is the one step that needs `sudo`, and it prompts on your
terminal.

**Seeding.** `dev_seed_command` in `config/kubeyard.yml` tells kubeyard how to
load development data. Because kubeyard already knows the namespace, seeding
targets the workspace's pod and database. `deploy` runs it automatically for a
database it has just created - which is therefore empty - and not otherwise.

## Limits worth knowing

- **Fixed `nodePort`s are cluster-global.** A Service pinning one cannot exist
  twice, so kubeyard skips it in the workspace and says so. The application is
  still reachable through whatever ingress you use.
- **HTTP routing from outside the cluster is not handled.** In-cluster calls work
  through the alias overlay; reaching a workspace from a browser needs your
  ingress to map the workspace hostname to the workspace namespace, which is
  specific to your setup.
- **`destroy` deletes a namespace.** Everything in it, including the database,
  goes. `undeploy` is the smaller hammer: it removes one project and restores
  its aliases.
- **Without a marker file, nothing changes.** No namespace flag is emitted and
  every command behaves exactly as it did before workspaces existed. This is
  covered by tests, not just by intent.
