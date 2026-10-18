import json
import os
import shutil
import subprocess
import unittest

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

PLUGIN_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "plugins", "vhPlayerAspectRatioFix")
PLUGIN_JS = os.path.join(PLUGIN_DIR, "vhPlayerAspectRatioFix.js")


def plugin_exports():
    """Load the plugin script in Node and return its exported constants."""
    node = shutil.which("node")
    if node is None:
        raise AssertionError("node is required to run the vhPlayerAspectRatioFix tests")
    script = (
        "const m = require(process.argv[1]);"
        "process.stdout.write(JSON.stringify({ id: m.PLUGIN_ID, setting: m.SETTING_KEY,"
        " presets: m.PRESETS.map((p) => p.label) }));"
    )
    out = subprocess.run([node, "-e", script, os.path.abspath(PLUGIN_JS)], check=True, capture_output=True, text=True)
    return json.loads(out.stdout)


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exports = plugin_exports()

    def test_menu_offers_exactly_the_agreed_presets_in_order(self):
        self.assertEqual(self.exports["presets"], ["16:9", "4:3", "1:1", "Original"])

    def test_plugin_id_matches_manifest_filename(self):
        self.assertEqual(self.exports["id"], "vhPlayerAspectRatioFix")
        self.assertTrue(os.path.exists(os.path.join(PLUGIN_DIR, self.exports["id"] + ".yml")))

    @unittest.skipIf(yaml is None, "PyYAML not installed")
    def test_manifest_declares_the_shrink_to_fit_setting_the_script_reads(self):
        with open(os.path.join(PLUGIN_DIR, "vhPlayerAspectRatioFix.yml"), encoding="utf-8") as handle:
            manifest = yaml.safe_load(handle)
        self.assertEqual(manifest["name"], "VH - Player Aspect Ratio Fix")
        self.assertEqual(manifest["ui"]["javascript"], ["vhPlayerAspectRatioFix.js"])
        setting = manifest["settings"][self.exports["setting"]]
        self.assertEqual(setting["type"], "BOOLEAN")
        self.assertEqual(setting["displayName"], "Shrink to fit")


if __name__ == "__main__":
    unittest.main()
