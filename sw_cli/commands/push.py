from sw_cli.commands.devel import BaseDevelCommand


class PushCommand(BaseDevelCommand):
    """
    Runs `docker push` on docker image built by build command. It also tags image as latest adn push it as well.
    Can be overridden in <project_dir>/sripts/push.

    If sw-cli is set up in development mode it uses minikube as docker host.

    Normally you want to run it only in production.
    """
    custom_script_name = 'push'

    def run_default(self):
        self.docker_with_output('push', self.image)
        self.docker_with_output('tag', self.image, self.latest_image)
        self.docker_with_output('push', self.latest_image)
