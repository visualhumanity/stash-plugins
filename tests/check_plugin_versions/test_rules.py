import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))

from check_plugin_versions import check  # noqa: E402


class VersionBumpTest(unittest.TestCase):
    def test_changed_plugin_without_bump_fails(self):
        failures = check(
            target="develop",
            changed=["plugins/pluginA/pluginA.js"],
            base={"pluginA": "1.0.0"},
            head={"pluginA": "1.0.0"},
        )
        self.assertEqual(failures, ["pluginA: version 1.0.0 not bumped (base 1.0.0)"])

    def test_lower_version_fails(self):
        failures = check(
            target="develop",
            changed=["plugins/pluginA/pluginA.js"],
            base={"pluginA": "1.2.0"},
            head={"pluginA": "1.1.9"},
        )
        self.assertEqual(failures, ["pluginA: version 1.1.9 is lower than base 1.2.0"])

    def test_valid_bumps_pass(self):
        for new in ["1.2.4", "1.3.0", "2.0.0", "1.2.9", "3.0.0"]:
            with self.subTest(version=new):
                failures = check(
                    target="develop",
                    changed=["plugins/pluginA/pluginA.js"],
                    base={"pluginA": "1.2.3"},
                    head={"pluginA": new},
                )
                self.assertEqual(failures, [])

    def test_malformed_base_version_fails(self):
        failures = check(
            target="main",
            changed=["plugins/pluginA/pluginA.js"],
            base={"pluginA": "1.0"},
            head={"pluginA": "1.0.1"},
        )
        self.assertEqual(failures, ["pluginA: base version '1.0' on main is not X.Y.Z, cannot compare"])

    def test_target_must_be_develop_or_main(self):
        with self.assertRaises(ValueError):
            check(target="feature/x", changed=[], base={}, head={})

    def test_numeric_comparison_not_text(self):
        failures = check(
            target="develop",
            changed=["plugins/pluginA/pluginA.js"],
            base={"pluginA": "1.9.0"},
            head={"pluginA": "1.10.0"},
        )
        self.assertEqual(failures, [])


class MalformedVersionTest(unittest.TestCase):
    def test_malformed_versions_fail_with_value_named(self):
        for bad in ["1.0", "v1.0.0", "01.0.0", "1.0.0-rc.1", "1.0.0+abc", "1.0.0.0", ""]:
            with self.subTest(version=bad):
                failures = check(
                    target="develop",
                    changed=["plugins/pluginA/pluginA.js"],
                    base={"pluginA": "1.0.0"},
                    head={"pluginA": bad},
                )
                self.assertEqual(
                    failures,
                    [f"pluginA: malformed version '{bad}' in plugins/pluginA/pluginA.yml (expected X.Y.Z)"],
                )

    def test_missing_version_fails(self):
        failures = check(
            target="develop",
            changed=["plugins/pluginA/pluginA.js"],
            base={"pluginA": "1.0.0"},
            head={"pluginA": None},
        )
        self.assertEqual(failures, ["pluginA: missing version in plugins/pluginA/pluginA.yml"])


class ExemptFilesTest(unittest.TestCase):
    def test_exempt_only_changes_pass_without_bump(self):
        for path in [
            "plugins/pluginA/README.md",
            "plugins/pluginA/readme",
            "plugins/pluginA/Readme.rst",
            "plugins/pluginA/CHANGELOG.txt",
            "plugins/pluginA/changelog",
            "plugins/pluginA/docs/usage.md",
            "plugins/pluginA/NOTES.TXT",
        ]:
            with self.subTest(path=path):
                failures = check(
                    target="develop",
                    changed=[path],
                    base={"pluginA": "1.0.0"},
                    head={"pluginA": "1.0.0"},
                )
                self.assertEqual(failures, [])

    def test_exempt_and_non_exempt_mix_requires_bump(self):
        failures = check(
            target="develop",
            changed=["plugins/pluginA/README.md", "plugins/pluginA/pluginA.py"],
            base={"pluginA": "1.0.0"},
            head={"pluginA": "1.0.0"},
        )
        self.assertEqual(failures, ["pluginA: version 1.0.0 not bumped (base 1.0.0)"])

    def test_non_code_assets_require_bump(self):
        for path in [
            "plugins/pluginA/pluginA.css",
            "plugins/pluginA/icon.png",
            "plugins/pluginA/strings.json",
            "plugins/pluginA/pluginA.yml",
            "plugins/pluginA/README_helper.js",
        ]:
            with self.subTest(path=path):
                failures = check(
                    target="develop",
                    changed=[path],
                    base={"pluginA": "1.0.0"},
                    head={"pluginA": "1.0.0"},
                )
                self.assertEqual(failures, ["pluginA: version 1.0.0 not bumped (base 1.0.0)"])


class ScopeTest(unittest.TestCase):
    def test_paths_outside_plugin_folders_are_ignored(self):
        failures = check(
            target="develop",
            changed=[".github/workflows/deploy.yml", "tests/test_x.py", "build_site.sh", "CLAUDE.md", "plugins/.gitkeep"],
            base={},
            head={},
        )
        self.assertEqual(failures, [])

    def test_unchanged_plugin_with_malformed_version_is_ignored(self):
        failures = check(
            target="develop",
            changed=["plugins/pluginB/pluginB.js"],
            base={"pluginA": "1.0", "pluginB": "2.3.1"},
            head={"pluginA": "1.0", "pluginB": "2.4.0"},
        )
        self.assertEqual(failures, [])

    def test_older_copy_of_untouched_plugin_is_not_checked(self):
        # The feature branch was cut before develop bumped pluginA, and only changes pluginB.
        # pluginA isn't in the three-dot diff, so its older version on the branch doesn't matter.
        failures = check(
            target="develop",
            changed=["plugins/pluginB/pluginB.js", "plugins/pluginB/pluginB.yml"],
            base={"pluginA": "1.0.1", "pluginB": "2.3.1"},
            head={"pluginA": "1.0.0", "pluginB": "2.4.0"},
        )
        self.assertEqual(failures, [])

    def test_every_failing_plugin_is_reported(self):
        failures = check(
            target="develop",
            changed=["plugins/pluginB/pluginB.js", "plugins/pluginA/pluginA.js", "plugins/pluginC/pluginC.js"],
            base={"pluginA": "1.0.0", "pluginB": "2.0.0", "pluginC": "3.0.0"},
            head={"pluginA": "1.0.0", "pluginB": "1.9.0", "pluginC": "3.0.1"},
        )
        self.assertEqual(
            failures,
            [
                "pluginA: version 1.0.0 not bumped (base 1.0.0)",
                "pluginB: version 1.9.0 is lower than base 2.0.0",
            ],
        )


class NewAndRemovedPluginTest(unittest.TestCase):
    def check_new(self, target, version):
        return check(
            target=target,
            changed=["plugins/pluginN/pluginN.yml", "plugins/pluginN/pluginN.js"],
            base={},
            head={"pluginN": version},
        )

    def test_new_plugin_on_develop_must_be_pre_1_0(self):
        for version in ["0.1.0", "0.5.3", "0.10.0"]:
            with self.subTest(version=version):
                self.assertEqual(self.check_new("develop", version), [])
        for version in ["0.0.1", "0.0.9", "1.0.0", "2.1.0"]:
            with self.subTest(version=version):
                self.assertEqual(
                    self.check_new("develop", version),
                    [f"pluginN: new plugin on develop must be 0.Y.Z, at least 0.1.0 (got {version})"],
                )

    def test_new_plugin_on_main_must_be_exactly_1_0_0(self):
        self.assertEqual(self.check_new("main", "1.0.0"), [])
        for version in ["0.3.0", "1.0.1", "1.1.0", "2.0.0"]:
            with self.subTest(version=version):
                self.assertEqual(
                    self.check_new("main", version),
                    [f"pluginN: new plugin on main must be 1.0.0 (got {version})"],
                )

    def test_new_plugin_with_malformed_version_fails(self):
        self.assertEqual(
            self.check_new("develop", "0.1"),
            ["pluginN: malformed version '0.1' in plugins/pluginN/pluginN.yml (expected X.Y.Z)"],
        )

    def test_deleted_plugin_passes(self):
        failures = check(
            target="develop",
            changed=["plugins/pluginA/pluginA.yml", "plugins/pluginA/pluginA.js"],
            base={"pluginA": "1.4.0"},
            head={},
        )
        self.assertEqual(failures, [])

    def test_renamed_folder_is_checked_as_new_plugin(self):
        changed = [
            "plugins/oldName/oldName.yml",
            "plugins/oldName/oldName.js",
            "plugins/newName/newName.yml",
            "plugins/newName/newName.js",
        ]
        self.assertEqual(
            check(target="develop", changed=changed, base={"oldName": "1.2.0"}, head={"newName": "0.1.0"}),
            [],
        )
        self.assertEqual(
            check(target="develop", changed=changed, base={"oldName": "1.2.0"}, head={"newName": "1.2.0"}),
            ["newName: new plugin on develop must be 0.Y.Z, at least 0.1.0 (got 1.2.0)"],
        )


if __name__ == "__main__":
    unittest.main()
