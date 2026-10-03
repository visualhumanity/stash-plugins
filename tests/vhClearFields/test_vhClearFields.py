import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "..", "plugins", "vhClearFields"),
)

import vhClearFields as cf  # noqa: E402


class FakeLog:
    def __init__(self):
        self.infos, self.errors, self.progress_values = [], [], []

    def info(self, msg):
        self.infos.append(msg)

    def error(self, msg):
        self.errors.append(msg)

    def progress(self, value):
        self.progress_values.append(value)


class FakeStash:
    def __init__(self, fail_ids=()):
        self.calls = []
        self.fail_ids = set(fail_ids)

    def update_scene(self, update_input):
        self.calls.append(update_input)
        if update_input["id"] in self.fail_ids:
            raise RuntimeError("boom")
        return update_input["id"]


class BuildUpdateInputTests(unittest.TestCase):
    def test_every_field_maps_to_its_empty_value(self):
        result = cf.build_update_input("7", list(cf.ALLOWED_FIELDS))
        self.assertEqual(
            result,
            {
                "id": "7",
                "title": "",
                "urls": [],
                "date": None,
                "director": "",
                "performer_ids": [],
                "studio_id": None,
                "details": "",
                "stash_ids": [],
                "code": "",
            },
        )

    def test_only_ticked_fields_are_sent(self):
        result = cf.build_update_input("7", ["title", "studio"])
        self.assertEqual(result, {"id": "7", "title": "", "studio_id": None})

    def test_never_sends_cover_tags_groups_or_markers(self):
        result = cf.build_update_input("7", list(cf.ALLOWED_FIELDS))
        for forbidden in ("cover_image", "tag_ids", "groups", "movies", "scene_markers"):
            self.assertNotIn(forbidden, result)

    def test_list_values_are_not_shared_between_calls(self):
        first = cf.build_update_input("1", ["urls"])
        first["urls"].append("https://example.com/x")
        second = cf.build_update_input("2", ["urls"])
        self.assertEqual(second["urls"], [])

    def test_duplicate_and_reordered_fields_give_same_result(self):
        a = cf.build_update_input("7", ["title", "date", "title"])
        b = cf.build_update_input("7", ["date", "title"])
        self.assertEqual(a, b)


class ValidateArgsTests(unittest.TestCase):
    def test_accepts_valid_args(self):
        ids, fields = cf.validate_args(
            {"sceneIds": ["1", "2"], "fields": ["title", "date"]}
        )
        self.assertEqual(ids, ["1", "2"])
        self.assertEqual(fields, ["title", "date"])

    def test_numeric_ids_become_strings(self):
        ids, _ = cf.validate_args({"sceneIds": [1, "2"], "fields": ["title"]})
        self.assertEqual(ids, ["1", "2"])

    def test_duplicate_ids_are_removed_keeping_order(self):
        ids, _ = cf.validate_args({"sceneIds": ["3", "1", "3", 1], "fields": ["title"]})
        self.assertEqual(ids, ["3", "1"])

    def test_duplicate_fields_are_removed_keeping_order(self):
        _, fields = cf.validate_args(
            {"sceneIds": ["1"], "fields": ["date", "title", "date"]}
        )
        self.assertEqual(fields, ["date", "title"])

    def test_unknown_field_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            cf.validate_args({"sceneIds": ["1"], "fields": ["title", "tags"]})
        self.assertIn("tags", str(ctx.exception))

    def test_empty_scene_ids_rejected(self):
        with self.assertRaises(ValueError):
            cf.validate_args({"sceneIds": [], "fields": ["title"]})

    def test_empty_fields_rejected(self):
        with self.assertRaises(ValueError):
            cf.validate_args({"sceneIds": ["1"], "fields": []})

    def test_missing_keys_rejected(self):
        with self.assertRaises(ValueError):
            cf.validate_args({})

    def test_non_list_values_rejected(self):
        with self.assertRaises(ValueError):
            cf.validate_args({"sceneIds": "1", "fields": ["title"]})
        with self.assertRaises(ValueError):
            cf.validate_args({"sceneIds": ["1"], "fields": "title"})

    def test_non_numeric_scene_id_rejected(self):
        with self.assertRaises(ValueError):
            cf.validate_args({"sceneIds": ["abc"], "fields": ["title"]})


class RunTests(unittest.TestCase):
    def test_updates_each_scene_once_with_only_ticked_fields(self):
        stash, log = FakeStash(), FakeLog()
        cleared, failed = cf.run(stash, ["1", "2"], ["title"], log)
        self.assertEqual((cleared, failed), (2, []))
        self.assertEqual(
            stash.calls,
            [{"id": "1", "title": ""}, {"id": "2", "title": ""}],
        )

    def test_failure_does_not_stop_remaining_scenes(self):
        stash, log = FakeStash(fail_ids={"2"}), FakeLog()
        cleared, failed = cf.run(stash, ["1", "2", "3"], ["title"], log)
        self.assertEqual(cleared, 2)
        self.assertEqual(failed, ["2"])
        self.assertEqual([c["id"] for c in stash.calls], ["1", "2", "3"])
        self.assertTrue(any("2" in e for e in log.errors))

    def test_progress_reaches_one(self):
        stash, log = FakeStash(), FakeLog()
        cf.run(stash, ["1", "2", "3", "4"], ["title"], log)
        self.assertEqual(log.progress_values[-1], 1.0)
        self.assertEqual(log.progress_values, sorted(log.progress_values))


if __name__ == "__main__":
    unittest.main()
