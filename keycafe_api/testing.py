import tempfile
from pathlib import Path
from django.test import SimpleTestCase, override_settings


class UpstreamIsolatedTestCase(SimpleTestCase):
    def setUp(self):
        super().setUp()
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        override = override_settings(TABLEAU_UPSTREAM_DB=str(Path(directory.name) / 'upstream.sqlite3'))
        override.enable()
        self.addCleanup(override.disable)
