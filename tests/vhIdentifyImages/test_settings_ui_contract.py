"""The settings UI script, the manifest and the backend must agree on setting keys and values."""

import os
import re
import sys
import unittest

from .stash_stub import PLUGIN_DIR

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

sys.path.insert(0, PLUGIN_DIR)

import identify_settings  # noqa: E402

IDENTIFY_ORDER = ["Title", "Code", "Details", "Date", "URLs", "Studio", "Performers", "Tags"]


def read_plugin_file(name):
    with open(os.path.join(PLUGIN_DIR, name), encoding="utf-8") as handle:
        return handle.read()


def js_list(js, name):
    block = js[js.index(f"const {name} = [") : js.index("];", js.index(f"const {name} = ["))]
    return re.findall(r'"(\w+)"', block)


def js_fields(js):
    block = js[js.index("const FIELDS = [") : js.index("];", js.index("const FIELDS = ["))]
    rows = re.findall(
        r'\{ key: "(\w+)", setting: "(\w+)", label: "([^"]+)"(?:, create: "(\w+)")? \}',
        block,
    )
    return [{"key": k, "setting": s, "label": label, "create": c or None} for k, s, label, c in rows]


class ScriptContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = read_plugin_file("vhIdentifyImages.js")
        cls.fields = js_fields(cls.js)

    def test_fields_follow_identify_order(self):
        self.assertEqual([f["label"] for f in self.fields], IDENTIFY_ORDER)

    def test_js_fields_match_backend_field_settings(self):
        self.assertEqual({f["key"]: f["setting"] for f in self.fields}, identify_settings.FIELD_SETTINGS)

    def test_create_missing_only_for_studio_performers_and_tags(self):
        creates = {f["key"]: f["create"] for f in self.fields if f["create"]}
        self.assertEqual(
            creates,
            {"studio": "createMissingStudios", "performers": "createMissingPerformers", "tags": "createMissingTags"},
        )

    def test_strategies_and_default_match_the_backend(self):
        block = self.js[self.js.index("const STRATEGIES = [") : self.js.index("];", self.js.index("const STRATEGIES = ["))]
        values = re.findall(r'value: "(\w+)"', block)
        self.assertEqual(tuple(values), identify_settings.FIELD_STRATEGIES)
        self.assertIn(f'const DEFAULT_STRATEGY = "{identify_settings.DEFAULT_STRATEGY}";', self.js)

    def test_patch_chain_is_called_with_props_and_ctx(self):
        # Stash appends the next function in the PluginSettings patch chain as the last
        # argument; calling the chain with props alone hands the next plugin's patch our
        # function in place of its own and crashes the Settings page.
        # calls of the chain, not the boundary's render() method definition
        calls = re.findall(r"\b(render|original)\(([^()]*)\)(?!\s*\{)", self.js)
        self.assertTrue(calls)
        for name, args in calls:
            top_level = re.sub(r"\{[^{}]*\}", "OBJECT", args)
            self.assertEqual(len([a for a in top_level.split(",") if a.strip()]), 2, f"{name}({args})")
        self.assertIn("render({ pluginID, settings }, undefined)", self.js)

    def test_custom_layout_falls_back_to_plain_settings(self):
        self.assertIn("class SettingsBoundary extends React.Component", self.js)
        self.assertIn("static getDerivedStateFromError()", self.js)
        self.assertIn("h(PluginSettings, { pluginID, settings, [PLAIN_FLAG]: true })", self.js)
        self.assertIn("if (props.pluginID !== PLUGIN_ID || props[PLAIN_FLAG]) {", self.js)

    def test_patch_is_limited_to_this_plugin(self):
        self.assertIn('const PLUGIN_ID = "vhIdentifyImages";', self.js)
        self.assertIn('patch.instead("PluginSettings"', self.js)
        self.assertIn("if (props.pluginID !== PLUGIN_ID || props[PLAIN_FLAG]) {\n      return original(props, ctx);", self.js)


@unittest.skipIf(yaml is None, "PyYAML not installed")
class ManifestContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = yaml.safe_load(read_plugin_file("vhIdentifyImages.yml"))
        cls.js = read_plugin_file("vhIdentifyImages.js")
        cls.fields = js_fields(cls.js)

    def test_manifest_field_keys_match_the_script(self):
        manifest_fields = {k for k in self.manifest["settings"] if k.startswith("field")}
        self.assertEqual(manifest_fields, {f["setting"] for f in self.fields})
        manifest_creates = {k for k in self.manifest["settings"] if k.startswith("createMissing")}
        self.assertEqual(manifest_creates, {f["create"] for f in self.fields if f["create"]})

    def test_script_places_every_manifest_setting_once(self):
        placed = js_list(self.js, "BEFORE_FIELDS") + js_list(self.js, "AFTER_FIELDS")
        for f in self.fields:
            placed.append(f["setting"])
            if f["create"]:
                placed.append(f["create"])
        self.assertEqual(sorted(placed), sorted(self.manifest["settings"]))

    def test_field_types_are_what_the_script_saves(self):
        for f in self.fields:
            self.assertEqual(self.manifest["settings"][f["setting"]]["type"], "STRING")
            if f["create"]:
                self.assertEqual(self.manifest["settings"][f["create"]]["type"], "BOOLEAN")

    def test_fallback_display_names_align_with_identify(self):
        for f in self.fields:
            self.assertEqual(self.manifest["settings"][f["setting"]]["displayName"], f"Field option: {f['label']}")

    def test_descriptions_use_default_wording(self):
        for key, entry in self.manifest["settings"].items():
            self.assertIn("Default:", entry["description"], key)
            self.assertNotIn("Empty means", entry["description"], key)

    def test_ui_assets_exist(self):
        ui = self.manifest["ui"]
        for asset in ui["javascript"] + ui["css"]:
            self.assertTrue(os.path.exists(os.path.join(PLUGIN_DIR, asset)), asset)


if __name__ == "__main__":
    unittest.main()
