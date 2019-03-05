import os

DEFAULT_KUBEYARD_PROJECT_DIR = '.'
DEFAULT_KUBEYARD_SCRIPTS_DIR = 'scripts'
DEFAULT_SWCLI_CONTEXT_FILEPATH = 'config/sw_cli.yml'  # TODO: remove legacy
DEFAULT_KUBEYARD_CONTEXT_FILEPATH = 'config/kubeyard.yml'
DEFAULT_SWCLI_USER_CONTEXT_FILEPATH = '.sw_cli/context.yml'  # TODO: remove legacy
DEFAULT_KUBEYARD_USER_CONTEXT_FILEPATH = '.kubeyard/context.yml'
DEFAULT_KUBEYARD_LOG_LEVEL = 'INFO'
DEFAULT_KUBEYARD_VM_DRIVER = 'none'
DEFAULT_KUBERNETES_DEPLOY_DIR = 'config/kubernetes/deploy'
DEFAULT_KUBERNETES_DEV_DEPLOY_OVERRIDES_DIR = 'config/kubernetes/development_overrides'
DEFAULT_KUBERNETES_DEV_SECRETS_DIR = 'config/kubernetes/dev_secrets'
KUBERNETES_PROD_SECRETS_DIR = (
        os.getenv('KUBEYARD_KUBERNETES_PROD_SECRETS_DIR') or
        os.getenv('SW_CLI_KUBERNETES_PROD_SECRETS_DIR') or  # TODO: remove legacy
        'kubernetes_secrets'
)
DEFAULT_DOCKER_REGISTRY_NAME = 'registry.hub.docker.com'
DEFAULT_PROJECT_NAME_PATTERN = '{project_name}'
DEFAULT_KUBE_SERVICE_NAME_PATTERN = '{dashed_project_name}'
DEFAULT_KUBE_SERVICE_PORT = '80'
DEFAULT_KUBE_LIVE_RELOAD_PORT = '30555'
DEFAULT_DEV_POSTGRES_NAME = 'kubernetes-postgres'
DEFAULT_DEV_PUBSUB_NAME = 'kubernetes-pubsub'
DEFAULT_DEV_REDIS_NAME = 'kubernetes-redis'
DEFAULT_DEV_ELASTIC_NAME = 'kubernetes-es'
DEFAULT_DEV_CASSANDRA_NAME = 'kubernetes-cassandra'
DEFAULT_DEV_TLD = 'testing'
DEFAULT_DEV_DOMAINS = ()
DEFAULT_TEST_DATABASE_IMAGE = 'postgres:10.3'
DEFAULT_TEST_DATABASE_NAME = 'test'
DEFAULT_TEST_MIGRATION_COMMAND = 'migrate_for_tests'
DEFAULT_TEST_COMMAND = 'run_tests'
