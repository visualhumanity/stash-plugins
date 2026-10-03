import io
import json
import os
import re
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

PLUGIN_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "plugins", "vhClearFields")
sys.path.insert(0, PLUGIN_DIR)

import vhClearFields as cf  # noqa: E402


def read_plugin_file(name):
    with open(os.path.join(PLUGIN_DIR, name), encoding="utf-8") as handle:
        return handle.read()


class StashStub:
    """Local HTTP server standing in for Stash's /graphql endpoint."""

    def __init__(self, responder=None):
        self.requests = []
        stub = self
        self.responder = responder or (lambda body: {"data": {"sceneUpdate": {"id": body["variables"]["input"]["id"]}}})

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers["Content-Length"])
                body = json.loads(self.rfile.read(length))
                stub.requests.append({"path": self.path, "headers": dict(self.headers), "body": body})
                payload = json.dumps(stub.responder(body)).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()

    def connection(self, **overrides):
        conn = {"Scheme": "http", "Host": "127.0.0.1", "Port": self.port}
        conn.update(overrides)
        return conn


class StashClientTests(unittest.TestCase):
    def test_posts_scene_update_to_graphql_with_the_input(self):
        with StashStub() as stub:
            result = cf.StashClient(stub.connection()).update_scene({"id": "7", "title": ""})
        request = stub.requests[0]
        self.assertEqual(request["path"], "/graphql")
        self.assertIn("sceneUpdate", request["body"]["query"])
        self.assertEqual(request["body"]["variables"], {"input": {"id": "7", "title": ""}})
        self.assertEqual(result, {"id": "7"})

    def test_sends_session_cookie_when_given(self):
        with StashStub() as stub:
            conn = stub.connection(SessionCookie={"Name": "session", "Value": "abc"})
            cf.StashClient(conn).update_scene({"id": "1"})
        self.assertEqual(stub.requests[0]["headers"]["Cookie"], "session=abc")

    def test_no_cookie_header_without_session_cookie(self):
        with StashStub() as stub:
            cf.StashClient(stub.connection(SessionCookie=None)).update_scene({"id": "1"})
        self.assertNotIn("Cookie", stub.requests[0]["headers"])

    def test_wildcard_host_becomes_localhost(self):
        for host in ("0.0.0.0", "::"):
            client = cf.StashClient({"Scheme": "http", "Host": host, "Port": 9999})
            self.assertEqual(client.url, "http://localhost:9999/graphql")

    def test_defaults_when_connection_is_sparse(self):
        self.assertEqual(cf.StashClient({}).url, "http://localhost:9999/graphql")

    def test_graphql_errors_raise_with_message(self):
        responder = lambda body: {"errors": [{"message": "scene not found"}, {"message": "second"}]}  # noqa: E731
        with StashStub(responder) as stub:
            with self.assertRaises(RuntimeError) as ctx:
                cf.StashClient(stub.connection()).update_scene({"id": "1"})
        self.assertIn("scene not found", str(ctx.exception))
        self.assertIn("second", str(ctx.exception))

    def test_unreachable_server_raises(self):
        with StashStub() as stub:
            conn = stub.connection()
        with self.assertRaises(Exception):
            cf.StashClient(conn).update_scene({"id": "1"})


class LogTests(unittest.TestCase):
    def capture(self, method, value):
        buffer = io.StringIO()
        with mock.patch.object(sys, "stderr", buffer):
            getattr(cf.Log(), method)(value)
        return buffer.getvalue()

    def test_levels_use_stash_raw_protocol(self):
        self.assertEqual(self.capture("info", "hi"), "\x01i\x02hi\n")
        self.assertEqual(self.capture("error", "bad"), "\x01e\x02bad\n")
        self.assertEqual(self.capture("progress", 0.5), "\x01p\x020.5\n")


class MainTests(unittest.TestCase):
    def run_main(self, payload):
        stderr = io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))), mock.patch.object(
            sys, "stderr", stderr
        ):
            cf.main()
        return stderr.getvalue()

    def test_wrong_mode_does_nothing(self):
        with StashStub() as stub:
            out = self.run_main({"args": {"mode": "other"}, "server_connection": stub.connection()})
        self.assertIn("unrecognised task mode", out)
        self.assertEqual(stub.requests, [])

    def test_invalid_args_are_refused_without_calling_stash(self):
        with StashStub() as stub:
            args = {"mode": cf.TASK_MODE, "sceneIds": ["1"], "fields": ["bogus"]}
            out = self.run_main({"args": args, "server_connection": stub.connection()})
        self.assertIn("refusing to run", out)
        self.assertEqual(stub.requests, [])

    def test_end_to_end_clears_ticked_fields_on_each_scene(self):
        with StashStub() as stub:
            args = {"mode": cf.TASK_MODE, "sceneIds": [3, "4"], "fields": ["studio", "title"]}
            out = self.run_main({"args": args, "server_connection": stub.connection()})
        inputs = [r["body"]["variables"]["input"] for r in stub.requests]
        self.assertEqual(inputs, [{"id": "3", "studio_id": None, "title": ""}, {"id": "4", "studio_id": None, "title": ""}])
        self.assertIn("cleared 2, failed 0", out)

    def test_failures_are_reported_and_batch_continues(self):
        def responder(body):
            if body["variables"]["input"]["id"] == "3":
                return {"errors": [{"message": "nope"}]}
            return {"data": {"sceneUpdate": {"id": "4"}}}

        with StashStub(responder) as stub:
            args = {"mode": cf.TASK_MODE, "sceneIds": ["3", "4"], "fields": ["title"]}
            out = self.run_main({"args": args, "server_connection": stub.connection()})
        self.assertEqual(len(stub.requests), 2)
        self.assertIn("cleared 1, failed 1", out)
        self.assertIn("failed scene ids: 3", out)


def parse_js_fields(js):
    """Parse the FIELDS table rows from the UI file."""
    block = js[js.index("const FIELDS = [") : js.index("];", js.index("const FIELDS = ["))]
    rows = re.findall(
        r'\{ key: "(\w+)", setting: "(\w+)", label: "([^"]+)", input: "(\w+)", empty: \(\) => (.+?) \}',
        block,
    )
    return rows


EMPTY_LITERALS = {'""': "", "[]": [], "null": None}


class UiBackendContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = read_plugin_file("vhClearFields.js")
        cls.rows = parse_js_fields(cls.js)

    def test_js_parsed_every_field(self):
        self.assertEqual(len(self.rows), len(cf.FIELD_CLEARS))

    def test_js_fields_match_backend_field_clears(self):
        for key, _setting, _label, input_key, empty in self.rows:
            self.assertIn(key, cf.FIELD_CLEARS)
            backend_key, factory = cf.FIELD_CLEARS[key]
            self.assertEqual(input_key, backend_key, key)
            self.assertEqual(EMPTY_LITERALS[empty], factory(), key)

    def test_js_field_order_matches_backend(self):
        self.assertEqual([r[0] for r in self.rows], list(cf.ALLOWED_FIELDS))

    def test_plugin_and_task_identifiers_match_manifest(self):
        plugin_id = re.search(r'const PLUGIN_ID = "(\w+)"', self.js).group(1)
        task_name = re.search(r'const TASK_NAME = "([^"]+)"', self.js).group(1)
        self.assertEqual(plugin_id, cf.PLUGIN_ID)
        yml = read_plugin_file("vhClearFields.yml")
        self.assertTrue(os.path.exists(os.path.join(PLUGIN_DIR, plugin_id + ".yml")))
        self.assertIn(f"- name: {task_name}\n", yml)
        self.assertIn(f"mode: {cf.TASK_MODE}", yml)

    def test_task_is_queued_with_arguments_the_backend_accepts(self):
        self.assertIn("args_map: { sceneIds, fields: selected }", self.js)
        scene_ids, fields = cf.validate_args({"sceneIds": ["1"], "fields": list(cf.ALLOWED_FIELDS)})
        self.assertEqual((scene_ids, fields), (["1"], list(cf.ALLOWED_FIELDS)))

    def test_scene_page_is_synchronous_and_list_is_queued(self):
        self.assertIn('patch.after("SceneList"', self.js)
        self.assertIn('patch.after("ScenePage"', self.js)
        self.assertRegex(self.js, r"sceneIds: \[props\.scene\.id\], sync: true")
        self.assertNotRegex(self.js, r"selectedIds[^\n]*sync")
        self.assertIn("GQL.useSceneUpdateMutation()", self.js)

    def test_scene_page_button_is_limited_to_the_edit_tab(self):
        self.assertIn("scene-edit-panel", self.js)
        self.assertIn("useEditTabActive(!!sync)", self.js)

    def test_dialog_wording(self):
        self.assertIn('h("span", null, "Clear fields")', self.js)
        self.assertIn("Select the fields to clear.", self.js)
        self.assertIn("This removes the following and cannot be undone.", self.js)
        self.assertIn('"Clear fields…"', self.js)


@unittest.skipIf(yaml is None, "PyYAML not installed")
class ManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = yaml.safe_load(read_plugin_file("vhClearFields.yml"))
        cls.rows = parse_js_fields(read_plugin_file("vhClearFields.js"))

    def test_required_top_level_fields(self):
        for key in ("name", "description", "version", "exec", "interface", "tasks", "settings", "ui"):
            self.assertIn(key, self.manifest)
        self.assertEqual(self.manifest["name"], "VH - Clear Fields")
        self.assertEqual(self.manifest["interface"], "raw")

    def test_no_third_party_dependency_is_declared(self):
        self.assertNotIn("requires: PythonDepManager", read_plugin_file("vhClearFields.yml"))

    def test_ui_assets_exist(self):
        for asset in self.manifest["ui"]["javascript"] + self.manifest["ui"]["css"]:
            self.assertTrue(os.path.exists(os.path.join(PLUGIN_DIR, asset)), asset)

    def test_settings_match_js_fields_one_to_one(self):
        self.assertEqual(set(self.manifest["settings"]), {row[1] for row in self.rows})

    def test_settings_wording(self):
        for _key, setting, label, _input, _empty in self.rows:
            entry = self.manifest["settings"][setting]
            self.assertEqual(entry["type"], "BOOLEAN")
            self.assertEqual(entry["displayName"], label)
            self.assertRegex(
                entry["description"],
                r"^Clear the .+ by default in the Clear fields dialog$",
            )
            self.assertNotIn("Pre-select", entry["displayName"])


if __name__ == "__main__":
    unittest.main()
