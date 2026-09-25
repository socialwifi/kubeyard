## 1.3.2 (unreleased)
---------------------

- The `global` ConfigMap's `base-domain` now follows the project's `dev_tld` instead of a
  hardcoded `testing`, and inside a workspace it is qualified with the workspace name
  (`<workspace>.ws.<dev_tld>`). `dev_tld` defaults to `testing`, so a project that has not
  set it is unaffected.


## 1.3.1 (2026-09-17)
---------------------

- `kubeyard workspace create` now creates the git worktree it attaches to, on a branch
  `ws-<name>` under `.worktrees/`, and prints the path. Run inside a worktree it attaches
  that one as before. The directory is configurable with `--worktree-root` or
  `KUBEYARD_WORKTREE_ROOT`, and `--print-path` prints the path alone so a shell function
  can `cd` into it. `workspace destroy` leaves the worktree alone.


## 1.3.0 (2026-09-17)
---------------------

- Add workspaces: `kubeyard workspace create|destroy|show|list|sync` deploy a project into an
  isolated `ws-<name>` namespace with its own development requirements, aliasing every other
  service back to `default`.
- Add `kubeyard undeploy` as the inverse of `deploy`.
- Add `kubeyard seed`, driven by `dev_seed_command` and `dev_seed_pod` in `config/kubeyard.yml`.
  `deploy` runs it automatically for a database it has just created, which is therefore empty;
  a redeploy finds the database present and does not seed again.
- Use the workspace name as an image tag suffix in development, so concurrent builds and tests
  do not collide.
- Require kubepy 1.21.0 for namespace support.
- Add a test suite.
- Drop Python 3.9, which is end of life, and add 3.13 and 3.14. Supported range is now
  3.10-3.14, enforced by `python_requires`.


## 1.2.3 (2026-06-16)
---------------------

- Update CockroachDB image tag.


## 1.2.2 (2026-06-15)
---------------------

- Make newer versions of CockroachDB work as test database.


## 1.2.1 (2026-04-20)
---------------------

- Fix command availability check for better cross-distro compatibility.


## 1.2.0 (2025-11-19)
---------------------

- Support newest minikube.


## 1.1.0 (2024-05-21)
---------------------

- Support applying HorizontalPodAutoscaler (via kubepy).
- Run linting with tox and GitHub Actions.
- Drop support for Python 3.7 and 3.8, add support for Python 3.12.


## 1.0.0 (2023-12-08)
----------------------

- Add support for "docker" driver in minikube.


## 0.13.0 (2023-11-08)
----------------------

- Allow using root of bucket, without forcing subdirectories.


## 0.12.0 (2023-09-06)
----------------------

- Support applying more resources (via kubepy).


## 0.11.1 (2023-02-16)
-------------------

- Freeze `sh` dependency due to breaking changes in new version.


0.11.0 (2023-02-08)
-------------------

- Fix getting minikube node IP without requiring sudo.
- Remove bind mounting minikube directories.
- Update kubepy to make it work on newest Python.
- Support stopping command like build on Docker 23.0.


0.10.0 (2023-02-07)
-------------------

- Support newest minikube.
- Support applying some CRDs (via kubepy).


0.9.0 (2022-04-12)
------------------

- Support newer CockroachDB.


0.8.0 (2020-01-03)
------------------

- Add support for Azure storage to deploy command.


0.7.1 (2020-01-02)
------------------

- Drop deprecated `--generic` flag for `update-requirements` command. 
- Extend meaning of pod argument in `shell` command.

0.7.0 (2019-08-27)
------------------

- Drop legacy update requirements method.


0.6.0 (2019-07-04)
------------------

- Display logs when a job fails.


0.5.1 (2019-04-16)
------------------

- Fix YAMLLoadWarning: https://msg.pyyaml.org/load


0.5.0 (2019-03-15)
------------------

- Add rabbitmq as a requirement.


0.4.0 (2019-03-06)
------------------

- Add generic method for `update-requirements` command.
- Improve django template.
- Remove git dependency.
- Drop support for legacy pip (`--before3.6.0-5` in update requirements command).


0.3.0 (2019-03-04)
------------------

- Fix support for CronJobs.
- Use newest version of minikube.
- Add support for uploading static files to S3.
- Add docker_args option to build command.
- Add optional NAME argument to variables command.

0.2.3 (2018-12-18)
------------------

- Fix README Markdown rendering on pypi.


0.2.2 (2018-12-18)
------------------

- Various fixes for Django template.


0.2.1 (2018-12-17)
------------------

- Add template for a Django project.


0.2.0 (2018-12-16)
------------------

- Initial public release.
