import os
import unittest

PLUGINS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "plugins")


class ReadmePresenceTest(unittest.TestCase):
    # ADR 0002: every plugin has a README.md in its own folder.
    def test_every_plugin_folder_has_readme(self):
        # Skip caches and hidden folders (__pycache__, .pytest_cache), which aren't plugins
        folders = sorted(
            name
            for name in os.listdir(PLUGINS_DIR)
            if os.path.isdir(os.path.join(PLUGINS_DIR, name)) and not name.startswith((".", "__"))
        )
        self.assertTrue(folders, "no plugin folders found")
        missing = [f for f in folders if not os.path.isfile(os.path.join(PLUGINS_DIR, f, "README.md"))]
        self.assertEqual(missing, [], f"plugin folders without README.md: {', '.join(missing)}")
