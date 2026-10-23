"""Entry-point tests for VH - Identify Images.

Each test runs the plugin script with the stdin JSON Stash sends, against a
local stand-in for Stash's GraphQL endpoint, and checks the calls that go out
and the log that comes back.
"""

import os
import unittest

from .stash_stub import PLUGIN_DIR, FakeStash, image, run_plugin

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

SUB = "/data/example/reddit/r_ExampleSub/"
OTHER = "/data/example/reddit/r_OtherSub/"
TWITTER = "/data/example/twitter/u_example_user/"

SINGLE_FIELDS = ("title", "code", "details", "date")
SETTING_FOR = {"title": "fieldTitle", "code": "fieldCode", "details": "fieldDetails", "date": "fieldDate"}
SCRAPED_VALUE = {
    "title": "Example Image",
    "code": "abc123",
    "details": "Example details",
    "date": "2024-01-02",
}
EXISTING_VALUE = {
    "title": "Old Title",
    "code": "old999",
    "details": "Old details",
    "date": "2020-05-06",
}


def messages(log, level=None):
    return [m for lvl, m in log if level is None or lvl == level]


def joined(log, level=None):
    return "\n".join(messages(log, level))


class ScrapeSourceTests(unittest.TestCase):
    def test_default_scraper_id_is_gallerydlreddit(self):
        with FakeStash([image(1, SUB + "a.jpg")], settings={}) as stub:
            run_plugin(stub)
        self.assertEqual(stub.scrape_sources(), [{"scraper_id": "GalleryDlReddit"}])
        self.assertEqual(stub.scraped_ids(), ["1"])

    def test_default_applies_when_no_settings_were_ever_saved(self):
        with FakeStash([image(1, SUB + "a.jpg")], settings=None) as stub:
            run_plugin(stub)
        self.assertEqual(stub.scrape_sources(), [{"scraper_id": "GalleryDlReddit"}])

    def test_configured_scraper_id_is_used(self):
        with FakeStash([image(1, SUB + "a.jpg")], settings={"scraperId": " ExampleScraper "}) as stub:
            run_plugin(stub)
        self.assertEqual(stub.scrape_sources(), [{"scraper_id": "ExampleScraper"}])

    def test_first_scrape_result_is_used(self):
        scrapes = {"1": [{"title": "First"}, {"title": "Second"}]}
        with FakeStash([image(1, SUB + "a.jpg")], settings={}, scrapes=scrapes) as stub:
            run_plugin(stub)
        self.assertEqual(stub.updates(), [{"id": "1", "title": "First"}])


class FolderPrefixTests(unittest.TestCase):
    IMAGES = [
        image(1, SUB + "a.jpg"),
        image(2, OTHER + "b.jpg"),
        image(3, TWITTER + "c.jpg"),
        image(4, "/data/example/reddit/r_ExampleSubTwo/d.jpg"),
    ]

    def scraped_with(self, prefixes):
        with FakeStash(self.IMAGES, settings={"folderPrefixes": prefixes}) as stub:
            run_plugin(stub)
        return sorted(stub.scraped_ids())

    def test_one_prefix(self):
        self.assertEqual(self.scraped_with(SUB), ["1"])

    def test_several_prefixes(self):
        self.assertEqual(self.scraped_with(f"{SUB} | {TWITTER}"), ["1", "3"])

    def test_empty_setting_means_all_images(self):
        self.assertEqual(self.scraped_with(""), ["1", "2", "3", "4"])
        self.assertEqual(self.scraped_with(" | "), ["1", "2", "3", "4"])

    def test_unset_setting_means_all_images(self):
        with FakeStash(self.IMAGES, settings={}) as stub:
            run_plugin(stub)
        self.assertEqual(sorted(stub.scraped_ids()), ["1", "2", "3", "4"])
        for body in stub.calls("findImages"):
            self.assertNotIn("path", body["variables"].get("image_filter") or {})

    def test_prefix_is_matched_literally_from_the_start(self):
        images = [
            image(1, "/data/example/set (1) [a].b/x.jpg"),
            image(2, "/data/example/set 1 a.b/y.jpg"),
            image(3, "/other/data/example/set (1) [a].b/z.jpg"),
        ]
        with FakeStash(images, settings={"folderPrefixes": "/data/example/set (1) [a].b/"}) as stub:
            run_plugin(stub)
        self.assertEqual(stub.scraped_ids(), ["1"])

    def test_pages_through_large_libraries(self):
        images = [image(i, f"{SUB}{i:05d}.jpg") for i in range(1, 1206)]
        with FakeStash(images, settings={}) as stub:
            log = run_plugin(stub)
        self.assertEqual(len(stub.scraped_ids()), 1205)
        self.assertEqual(len(set(stub.scraped_ids())), 1205)
        self.assertIn("processed 1205", joined(log))


class SingleValueFieldTests(unittest.TestCase):
    def run_field(self, field, option, existing, scraped):
        settings = {} if option is None else {SETTING_FOR[field]: option}
        img = image(1, SUB + "a.jpg", **{field: existing})
        # photographer is never applied; it keeps the result non-empty
        scrape = {field: scraped, "photographer": "Example Photographer"}
        with FakeStash([img], settings=settings, scrapes={"1": [scrape]}) as stub:
            run_plugin(stub)
        return stub.updates()

    def test_unset_option_means_merge(self):
        for field in SINGLE_FIELDS:
            with self.subTest(field=field):
                self.assertEqual(
                    self.run_field(field, None, None, SCRAPED_VALUE[field]),
                    [{"id": "1", field: SCRAPED_VALUE[field]}],
                )
                self.assertEqual(self.run_field(field, None, EXISTING_VALUE[field], SCRAPED_VALUE[field]), [])

    def test_merge_sets_only_an_empty_field(self):
        for field in SINGLE_FIELDS:
            for empty in (None, ""):
                with self.subTest(field=field, empty=empty):
                    self.assertEqual(
                        self.run_field(field, "merge", empty, SCRAPED_VALUE[field]),
                        [{"id": "1", field: SCRAPED_VALUE[field]}],
                    )
            with self.subTest(field=field, existing=True):
                self.assertEqual(self.run_field(field, "merge", EXISTING_VALUE[field], SCRAPED_VALUE[field]), [])

    def test_overwrite_replaces_an_existing_value(self):
        for field in SINGLE_FIELDS:
            with self.subTest(field=field):
                self.assertEqual(
                    self.run_field(field, "overwrite", EXISTING_VALUE[field], SCRAPED_VALUE[field]),
                    [{"id": "1", field: SCRAPED_VALUE[field]}],
                )
                self.assertEqual(
                    self.run_field(field, "overwrite", None, SCRAPED_VALUE[field]),
                    [{"id": "1", field: SCRAPED_VALUE[field]}],
                )

    def test_ignore_never_sets(self):
        for field in SINGLE_FIELDS:
            for existing in (None, EXISTING_VALUE[field]):
                with self.subTest(field=field, existing=existing):
                    self.assertEqual(self.run_field(field, "ignore", existing, SCRAPED_VALUE[field]), [])

    def test_options_are_case_insensitive(self):
        self.assertEqual(
            self.run_field("title", " OverWrite ", "Old Title", "Example Image"),
            [{"id": "1", "title": "Example Image"}],
        )
        self.assertEqual(self.run_field("title", "IGNORE", None, "Example Image"), [])

    def test_scraped_but_empty_value_never_touches_the_field(self):
        for field in SINGLE_FIELDS:
            for option in ("merge", "overwrite", "ignore"):
                for scraped in (None, "", "   "):
                    with self.subTest(field=field, option=option, scraped=scraped):
                        self.assertEqual(self.run_field(field, option, EXISTING_VALUE[field], scraped), [])
                        self.assertEqual(self.run_field(field, option, None, scraped), [])

    def test_same_value_sends_no_update(self):
        for field in SINGLE_FIELDS:
            with self.subTest(field=field):
                self.assertEqual(self.run_field(field, "overwrite", SCRAPED_VALUE[field], SCRAPED_VALUE[field]), [])

    def test_fields_are_applied_independently(self):
        img = image(1, SUB + "a.jpg", title="Old Title", details="Old details")
        scrape = {"title": "Example Image", "code": "abc123", "details": "Example details", "date": "2024-01-02"}
        settings = {"fieldTitle": "overwrite", "fieldCode": "ignore", "fieldDetails": "merge"}
        with FakeStash([img], settings=settings, scrapes={"1": [scrape]}) as stub:
            run_plugin(stub)
        self.assertEqual(stub.updates(), [{"id": "1", "title": "Example Image", "date": "2024-01-02"}])


URL_A = "https://example.com/post/a"
URL_B = "https://example.com/post/b"
URL_C = "https://example.com/post/c"


def performer(stored_id, name):
    return {"stored_id": stored_id, "name": name}


def tag(stored_id, name):
    return {"stored_id": stored_id, "name": name}


def linked(entity_id, name):
    return {"id": entity_id, "name": name}


class UrlTests(unittest.TestCase):
    def run_urls(self, option, existing, scraped):
        settings = {} if option is None else {"fieldUrls": option}
        img = image(1, SUB + "a.jpg", urls=existing)
        with FakeStash([img], settings=settings, scrapes={"1": [{"title": "Example Image", "urls": scraped}]}) as stub:
            run_plugin(stub)
        return [{k: v for k, v in u.items() if k in ("id", "urls")} for u in stub.updates() if "urls" in u]

    def test_merge_adds_scraped_urls_not_already_present(self):
        self.assertEqual(
            self.run_urls("merge", [URL_A], [URL_B, URL_A, URL_C]),
            [{"id": "1", "urls": [URL_A, URL_B, URL_C]}],
        )

    def test_unset_option_means_merge(self):
        self.assertEqual(self.run_urls(None, [URL_A], [URL_B]), [{"id": "1", "urls": [URL_A, URL_B]}])

    def test_merge_with_nothing_new_changes_nothing(self):
        self.assertEqual(self.run_urls("merge", [URL_A, URL_B], [URL_B]), [])

    def test_overwrite_replaces_the_list(self):
        self.assertEqual(
            self.run_urls("overwrite", [URL_A, URL_B], [URL_C, URL_A]),
            [{"id": "1", "urls": [URL_C, URL_A]}],
        )

    def test_overwrite_with_only_known_urls_changes_nothing(self):
        # Identify only overwrites when a scraped URL is not already on the item
        self.assertEqual(self.run_urls("overwrite", [URL_A, URL_B], [URL_B]), [])

    def test_ignore_leaves_urls_alone(self):
        self.assertEqual(self.run_urls("ignore", [], [URL_A]), [])

    def test_empty_scraped_list_changes_nothing(self):
        for option in ("merge", "overwrite", "ignore"):
            for scraped in ([], None, [""]):
                with self.subTest(option=option, scraped=scraped):
                    self.assertEqual(self.run_urls(option, [URL_A], scraped), [])


class RelationshipTests(unittest.TestCase):
    """Performers and tags share the same rules; each test runs both."""

    FIELDS = {
        "performers": ("fieldPerformers", "performer_ids", performer),
        "tags": ("fieldTags", "tag_ids", tag),
    }

    def run_field(self, field, option, existing, scraped):
        setting, _key, _make = self.FIELDS[field]
        settings = {} if option is None else {setting: option}
        img = image(1, SUB + "a.jpg", **{field: existing})
        scrape = {"title": "Example Image", field: scraped}
        with FakeStash([img], settings=settings, scrapes={"1": [scrape]}) as stub:
            run_plugin(stub)
        return stub

    def update_ids(self, stub, field):
        key = self.FIELDS[field][1]
        return [u[key] for u in stub.updates() if key in u]

    def each_field(self):
        for field, (_setting, _key, make) in self.FIELDS.items():
            with self.subTest(field=field):
                yield field, make

    def test_merge_adds_matched_items_to_existing_links(self):
        for field, make in self.each_field():
            stub = self.run_field(field, "merge", [linked("5", "Existing")], [make("7", "Example"), make("5", "Existing")])
            self.assertEqual(self.update_ids(stub, field), [["5", "7"]])

    def test_unset_option_means_merge(self):
        for field, make in self.each_field():
            stub = self.run_field(field, None, [linked("5", "Existing")], [make("7", "Example")])
            self.assertEqual(self.update_ids(stub, field), [["5", "7"]])

    def test_merge_with_nothing_new_changes_nothing(self):
        for field, make in self.each_field():
            stub = self.run_field(field, "merge", [linked("5", "Existing"), linked("7", "Example")], [make("7", "Example")])
            self.assertEqual(self.update_ids(stub, field), [])

    def test_overwrite_replaces_the_links(self):
        for field, make in self.each_field():
            stub = self.run_field(field, "overwrite", [linked("5", "Existing")], [make("7", "Example"), make("8", "Example Two")])
            self.assertEqual(self.update_ids(stub, field), [["7", "8"]])

    def test_overwrite_with_the_same_links_in_another_order_changes_nothing(self):
        for field, make in self.each_field():
            stub = self.run_field(
                field, "overwrite", [linked("8", "Example Two"), linked("7", "Example")], [make("7", "Example"), make("8", "Example Two")]
            )
            self.assertEqual(self.update_ids(stub, field), [])

    def test_ignore_leaves_links_alone(self):
        for field, make in self.each_field():
            stub = self.run_field(field, "ignore", [], [make("7", "Example")])
            self.assertEqual(self.update_ids(stub, field), [])

    def test_empty_scraped_list_changes_nothing(self):
        for field, _make in self.each_field():
            for option in ("merge", "overwrite", "ignore"):
                for scraped in ([], None):
                    stub = self.run_field(field, option, [linked("5", "Existing")], scraped)
                    self.assertEqual(self.update_ids(stub, field), [], (option, scraped))

    def test_unmatched_items_are_dropped_and_not_created(self):
        for field, make in self.each_field():
            stub = self.run_field(field, "merge", [], [make(None, "u_example_user"), make("7", "Example")])
            self.assertEqual(self.update_ids(stub, field), [["7"]])
            self.assertEqual([m for m in stub.mutations() if "imageUpdate" not in m["query"]], [])

    def test_only_unmatched_items_under_merge_changes_nothing(self):
        for field, make in self.each_field():
            stub = self.run_field(field, "merge", [linked("5", "Existing")], [make(None, "u_example_user")])
            self.assertEqual(self.update_ids(stub, field), [])

    def test_overwrite_with_only_unmatched_items_clears_links_like_identify(self):
        for field, make in self.each_field():
            stub = self.run_field(field, "overwrite", [linked("5", "Existing")], [make(None, "u_example_user")])
            self.assertEqual(self.update_ids(stub, field), [[]])

    def test_only_image_updates_are_sent(self):
        for field, make in self.each_field():
            stub = self.run_field(field, "overwrite", [linked("5", "Existing")], [make("7", "Example"), make(None, "New")])
            self.assertEqual({m["query"].split("(")[0].split()[-1] for m in stub.mutations()}, {"ImageUpdate"})

    def test_invalid_options_are_refused(self):
        for setting in ("fieldUrls", "fieldPerformers", "fieldTags"):
            with self.subTest(setting=setting):
                with FakeStash([image(1, SUB + "a.jpg")], settings={setting: "append"}) as stub:
                    log = run_plugin(stub)
                self.assertIn(setting, joined(log, "e"))
                self.assertEqual(stub.calls("scrapeSingleImage"), [])
                self.assertEqual(stub.mutations(), [])

    def test_all_three_combine_into_one_update(self):
        img = image(1, SUB + "a.jpg", urls=[URL_A], performers=[linked("5", "Existing")], tags=[])
        scrape = {"urls": [URL_B], "performers": [performer("7", "Example")], "tags": [tag("9", "Example Tag")]}
        with FakeStash([img], settings={}, scrapes={"1": [scrape]}) as stub:
            run_plugin(stub)
        self.assertEqual(
            stub.updates(),
            [{"id": "1", "urls": [URL_A, URL_B], "performer_ids": ["5", "7"], "tag_ids": ["9"]}],
        )

    def test_dry_run_logs_url_performer_and_tag_changes_without_writing(self):
        img = image(1, SUB + "a.jpg", urls=[URL_A], performers=[linked("5", "Existing Performer")], tags=[linked("3", "Old Tag")])
        scrape = {
            "urls": [URL_B],
            "performers": [performer("7", "Example Performer"), performer(None, "u_example_user")],
            "tags": [tag("9", "Example Tag")],
        }
        settings = {"dryRun": True, "fieldTags": "overwrite"}
        with FakeStash([img], settings=settings, scrapes={"1": [scrape]}) as stub:
            log = run_plugin(stub)
        self.assertEqual(stub.mutations(), [])
        text = joined(log)
        self.assertIn(f"urls: ['{URL_A}'] -> ['{URL_A}', '{URL_B}']", text)
        self.assertIn("performers: ['Existing Performer'] -> ['Existing Performer', 'Example Performer']", text)
        self.assertIn("tags: ['Old Tag'] -> ['Example Tag']", text)
        self.assertIn("u_example_user", text)


class DryRunTests(unittest.TestCase):
    def test_dry_run_sends_no_update_and_logs_old_and_new_values(self):
        img = image(1, SUB + "a.jpg", title="Old Title")
        scrape = {"title": "Example Image", "date": "2024-01-02"}
        settings = {"dryRun": True, "fieldTitle": "overwrite"}
        with FakeStash([img], settings=settings, scrapes={"1": [scrape]}) as stub:
            log = run_plugin(stub)
        self.assertEqual(stub.calls("imageUpdate"), [])
        text = joined(log)
        self.assertIn("dry run", text.lower())
        self.assertIn("title: 'Old Title' -> 'Example Image'", text)
        self.assertIn("date: None -> '2024-01-02'", text)
        self.assertIn(SUB + "a.jpg", text)

    def test_dry_run_summary_counts_would_be_updates(self):
        images = [image(1, SUB + "a.jpg"), image(2, SUB + "b.jpg", title="Example Image")]
        scrapes = {"1": [{"title": "Example Image"}], "2": [{"title": "Example Image"}]}
        with FakeStash(images, settings={"dryRun": True}, scrapes=scrapes) as stub:
            log = run_plugin(stub)
        self.assertEqual(stub.calls("imageUpdate"), [])
        self.assertIn("processed 2, updated 1, unchanged 1, no result 0, failed 0", joined(log))


class ImageLimitTests(unittest.TestCase):
    IMAGES = [image(i, f"{SUB}{i}.jpg") for i in range(1, 6)]

    def scraped_with(self, settings):
        with FakeStash(self.IMAGES, settings=settings) as stub:
            run_plugin(stub)
        return stub.scraped_ids()

    def test_limit_stops_after_that_many_images(self):
        self.assertEqual(len(self.scraped_with({"imageLimit": 2})), 2)
        self.assertEqual(len(self.scraped_with({"imageLimit": 2.0})), 2)

    def test_zero_or_unset_means_no_limit(self):
        self.assertEqual(len(self.scraped_with({"imageLimit": 0})), 5)
        self.assertEqual(len(self.scraped_with({})), 5)

    def test_limit_above_the_image_count(self):
        self.assertEqual(len(self.scraped_with({"imageLimit": 50})), 5)


class InvalidSettingTests(unittest.TestCase):
    def assert_refused(self, settings, setting_name):
        with FakeStash([image(1, SUB + "a.jpg")], settings=settings, scrapes={"1": [{"title": "Example Image"}]}) as stub:
            log = run_plugin(stub)
        self.assertIn(setting_name, joined(log, "e"))
        self.assertEqual(stub.calls("scrapeSingleImage"), [])
        self.assertEqual(stub.calls("imageUpdate"), [])
        self.assertEqual(stub.calls("findImages"), [])

    def test_unknown_field_option(self):
        for field, setting in SETTING_FOR.items():
            with self.subTest(field=field):
                self.assert_refused({setting: "replace"}, setting)

    def test_non_numeric_limit(self):
        self.assert_refused({"imageLimit": "abc"}, "imageLimit")

    def test_negative_or_fractional_limit(self):
        self.assert_refused({"imageLimit": -1}, "imageLimit")
        self.assert_refused({"imageLimit": 2.5}, "imageLimit")

    def test_non_boolean_dry_run(self):
        self.assert_refused({"dryRun": "yes"}, "dryRun")

    def test_one_valid_and_one_invalid_setting_still_refuses(self):
        self.assert_refused({"fieldTitle": "overwrite", "fieldDate": "always"}, "fieldDate")


class FailureAndSummaryTests(unittest.TestCase):
    def test_failures_are_logged_and_the_run_continues_with_correct_counts(self):
        images = [
            image(1, SUB + "1.jpg"),
            image(2, SUB + "2.jpg"),
            image(3, SUB + "3.jpg"),
            image(4, SUB + "4.jpg", title="Example Image"),
            image(5, SUB + "5.jpg"),
            image(6, SUB + "6.jpg"),
        ]
        scrapes = {
            "1": [{"title": "Example Image"}],
            "3": [{"title": "Example Image"}],
            "4": [{"title": "Example Image"}],
            "5": [],
            "6": [{"title": "Example Image"}],
        }
        with FakeStash(images, settings={}, scrapes=scrapes, scrape_errors={"2"}, update_errors={"3"}) as stub:
            log = run_plugin(stub)
        self.assertEqual(stub.scraped_ids(), ["1", "2", "3", "4", "5", "6"])
        self.assertEqual([u["id"] for u in stub.updates()], ["1", "3", "6"])
        errors = joined(log, "e")
        self.assertIn("scraper failed for this image", errors)
        self.assertIn("update rejected", errors)
        self.assertIn(SUB + "2.jpg", errors)
        self.assertIn(SUB + "3.jpg", errors)
        self.assertIn("processed 6, updated 2, unchanged 1, no result 1, failed 2", joined(log))

    def test_result_with_no_usable_fields_counts_as_no_result(self):
        scrapes = {"1": [{"title": None, "date": "", "urls": []}]}
        with FakeStash([image(1, SUB + "a.jpg")], settings={}, scrapes=scrapes) as stub:
            log = run_plugin(stub)
        self.assertEqual(stub.calls("imageUpdate"), [])
        self.assertIn("processed 1, updated 0, unchanged 0, no result 1, failed 0", joined(log))

    def test_progress_is_reported_and_reaches_one(self):
        images = [image(i, f"{SUB}{i}.jpg") for i in range(1, 5)]
        with FakeStash(images, settings={}) as stub:
            log = run_plugin(stub)
        progress = [float(m) for m in messages(log, "p")]
        self.assertEqual(progress, sorted(progress))
        self.assertEqual(progress[-1], 1.0)

    def test_no_images_found(self):
        with FakeStash([], settings={}) as stub:
            log = run_plugin(stub)
        self.assertEqual(stub.calls("scrapeSingleImage"), [])
        self.assertIn("processed 0", joined(log))


class EntryPointTests(unittest.TestCase):
    def test_unknown_mode_does_nothing(self):
        with FakeStash([image(1, SUB + "a.jpg")], settings={}) as stub:
            log = run_plugin(stub, args={"mode": "other"})
        self.assertEqual(stub.requests, [])
        self.assertTrue(messages(log, "e"))

    def test_hook_events_are_ignored_for_now(self):
        args = {"hookContext": {"type": "Image.Create.Post", "id": "1"}}
        with FakeStash([image(1, SUB + "a.jpg")], settings={}) as stub:
            run_plugin(stub, args=args)
        self.assertEqual(stub.calls("scrapeSingleImage"), [])
        self.assertEqual(stub.calls("imageUpdate"), [])

    def test_session_cookie_is_sent_on_every_request(self):
        scrapes = {"1": [{"title": "Example Image"}]}
        with FakeStash([image(1, SUB + "a.jpg")], settings={}, scrapes=scrapes) as stub:
            conn = stub.connection(SessionCookie={"Name": "session", "Value": "example-cookie"})
            run_plugin(stub, connection=conn)
        self.assertTrue(stub.requests)
        for request in stub.requests:
            self.assertEqual(request["path"], "/graphql")
            self.assertEqual(request["headers"].get("Cookie"), "session=example-cookie")

    def test_wildcard_host_connects_to_localhost(self):
        with FakeStash([image(1, SUB + "a.jpg")], settings={}) as stub:
            run_plugin(stub, connection=stub.connection(Host="0.0.0.0"))
        self.assertEqual(stub.scraped_ids(), ["1"])

    def test_unreachable_server_logs_an_error(self):
        with FakeStash([], settings={}) as stub:
            conn = stub.connection()
        log = run_plugin(stub, connection=conn)
        self.assertTrue(messages(log, "e"))


def read_plugin_file(name):
    with open(os.path.join(PLUGIN_DIR, name), encoding="utf-8") as handle:
        return handle.read()


@unittest.skipIf(yaml is None, "PyYAML not installed")
class ManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read_plugin_file("vhIdentifyImages.yml")
        cls.manifest = yaml.safe_load(cls.text)

    def test_identity_and_version(self):
        self.assertEqual(self.manifest["name"], "VH - Identify Images")
        self.assertEqual(str(self.manifest["version"]), "0.1.0")
        self.assertEqual(self.manifest["interface"], "raw")
        self.assertEqual(self.manifest["exec"], ["python", "{pluginDir}/vhIdentifyImages.py"])
        self.assertTrue(self.manifest["description"])

    def test_one_task_running_the_identify_mode(self):
        tasks = self.manifest["tasks"]
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["defaultArgs"], {"mode": "identify"})

    def test_settings_and_types(self):
        expected = {
            "scraperId": "STRING",
            "folderPrefixes": "STRING",
            "fieldTitle": "STRING",
            "fieldCode": "STRING",
            "fieldDetails": "STRING",
            "fieldDate": "STRING",
            "fieldUrls": "STRING",
            "fieldPerformers": "STRING",
            "fieldTags": "STRING",
            "dryRun": "BOOLEAN",
            "imageLimit": "NUMBER",
        }
        settings = self.manifest["settings"]
        self.assertEqual({k: v["type"] for k, v in settings.items()}, expected)
        for key, entry in settings.items():
            self.assertTrue(entry.get("displayName"), key)
            self.assertTrue(entry.get("description"), key)
            self.assertNotIn("default", entry, key)

    def test_no_third_party_dependency_is_declared(self):
        self.assertNotIn("requires:", self.text)


if __name__ == "__main__":
    unittest.main()
