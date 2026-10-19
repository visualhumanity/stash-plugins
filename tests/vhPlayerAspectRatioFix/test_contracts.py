import os
import re
import unittest

from tests.vhPlayerAspectRatioFix.node_runner import PLUGIN_DIR, run_plugin

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


def plugin_exports():
    return run_plugin("{ id: plugin.PLUGIN_ID, setting: plugin.SETTING_KEY, presets: plugin.PRESETS.map((p) => p.label) }")


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exports = plugin_exports()

    def test_menu_offers_exactly_the_agreed_presets_in_order(self):
        self.assertEqual(self.exports["presets"], ["16:9", "4:3", "1:1", "Original"])

    def test_plugin_id_matches_manifest_filename(self):
        self.assertEqual(self.exports["id"], "vhPlayerAspectRatioFix")
        self.assertTrue(os.path.exists(os.path.join(PLUGIN_DIR, self.exports["id"] + ".yml")))

    def test_button_responds_to_touch_taps(self):
        # video.js cancels the click after a touch and fires "tap" on its components instead
        with open(os.path.join(PLUGIN_DIR, "vhPlayerAspectRatioFix.js"), encoding="utf-8") as handle:
            js = handle.read()
        self.assertRegex(js, re.compile(r'button\.on\(\s*\[\s*"tap",\s*"click"\s*\]'))

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
