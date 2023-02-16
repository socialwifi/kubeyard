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
