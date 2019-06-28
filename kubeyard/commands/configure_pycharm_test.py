from kubeyard.base_command import InitialisedRepositoryCommand


class ConfigurePycharmTest(InitialisedRepositoryCommand):
    def run(self):
        super().run()
        workspace_xml = self.project_dir / '.idea' / 'workspace.xml'
        if workspace_xml.exists():
            with workspace_xml.open() as f:
                if '<component name="RunManager"' in f.read():
                    print()

