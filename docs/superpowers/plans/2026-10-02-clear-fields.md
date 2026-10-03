# Clear Fields Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Stash plugin that bulk-clears user-chosen metadata fields on selected scenes, from a button inside Stash, running as a background task.

**Architecture:** One hybrid plugin, `vhClearFields`. A hand-written UI script adds a "Clear fields..." button (scene list selection and scene page), a field-picker modal and a confirmation modal, then queues a plugin task with `runPluginTask`. A Python raw-interface task receives the scene IDs and field keys and sends one `sceneUpdate` per scene containing only the ticked fields' empty values.

**Tech Stack:** Stash UI Plugin API (`window.PluginApi`, React via `createElement`, `react-bootstrap`), Python 3 stdlib only (`urllib` GraphQL client), `unittest` for tests.

**Spec:** `docs/superpowers/specs/2026-10-02-clear-fields-design.md`

## Global Constraints

- Plugin ID and directory: `vhClearFields`; the manifest is `plugins/vhClearFields/vhClearFields.yml` (ID comes from the `.yml` filename).
- Manifest requires `name`, `description` (single line) and `version`; use `version: 1.0`.
- Settings are BOOLEAN only, nine keys: `clearTitle`, `clearUrls`, `clearDate`, `clearDirector`, `clearPerformers`, `clearStudio`, `clearDetails`, `clearStashIds`, `clearCode`. Unset means off; the plugin must not assume a default.
- Field keys passed from UI to task (exact): `title`, `urls`, `date`, `director`, `performers`, `studio`, `details`, `stashIds`, `code`.
- `sceneUpdate` empty values (exact): `title: ""`, `urls: []`, `date: null`, `director: ""`, `performer_ids: []`, `studio_id: null`, `details: ""`, `stash_ids: []`, `code: ""`. Only ticked fields are sent. Never send cover, tags, groups, markers.
- Task name: `Clear scene fields`; task `defaultArgs`: `mode: vhClearFields`; task args: `sceneIds` (list), `fields` (list).
- JS is hand-written plain ES (no build step, no TypeScript), committed as-is.
- Python uses the stdlib only (no `PythonDepManager`/`stashapi`, so it runs on instances without git), `interface: raw`, logging through the raw-plugin stderr protocol.
- Modals reuse Stash's `ModalComponent` markup and class names; footer order is Cancel (secondary) then accept (primary on modal 1, danger on modal 2).
- No real Stash data, hostnames, usernames, paths or media names anywhere in tracked files, tests or docs. Use synthetic values (`Example Scene`, IDs like `"1"`, `$STASH_TEST_URL`). Manual testing only against the designated test instance, never production.
- Commit only when the user has asked for commits; stage files by name and read `git diff --cached` first. Do not push or open PRs unless asked.

## Review Focus

- Duplicate scene IDs in `sceneIds` must not cause double updates (deduplicate, keep order).
- Scene IDs may arrive as numbers or numeric strings; both must work and be sent to Stash as strings.
- An unknown field key must abort the whole task before any scene is touched (never partially apply a typo).
- Empty `sceneIds` or empty `fields` must do nothing and log an error, never "clear everything".
- One scene failing (deleted mid-run, GraphQL error) must not stop the remaining scenes; failures are counted and logged with the scene ID.
- Duplicate field keys and any ordering of `fields` must produce the same single update per scene.
- Selecting "all" on the list yields a large `sceneIds`; the task must handle a few thousand scenes (progress logged, no per-scene state kept beyond counters).

---

## File Structure

- `plugins/vhClearFields/vhClearFields.py`: backend task. Pure functions (`validate_args`, `build_update_input`, `run`) plus `main()`. `Log` and `StashClient` (stdlib `urllib` GraphQL client using `server_connection`) are used by `main()`; there are no third-party imports.
- `plugins/vhClearFields/vhClearFields.yml`: manifest (ui, exec, task, settings).
- `plugins/vhClearFields/vhClearFields.js`: UI: field table, modal shell, flow component, button, patches.
- `plugins/vhClearFields/vhClearFields.css`: floating button styling only.
- `plugins/vhClearFields/README.md`: settings, behaviour, limitations.
- `tests/vhClearFields/test_client_and_contracts.py`: regression tests added after the first manual round: `StashClient` and `Log` against a local stub server, `main()` end to end, manifest checks, and UI/backend contract checks (field table, task name, arguments, wording). Run with the same `unittest discover` command.
- `tests/vhClearFields/test_vhClearFields.py`: unit tests for the pure Python functions.
- Modify `CLAUDE.md` (plugin table row) and the spec (package layout and entry-point wording, see Task 4).

---

### Task 1: Backend task logic (TDD)

**Files:**
- Create: `plugins/vhClearFields/vhClearFields.py`
- Create: `tests/vhClearFields/test_vhClearFields.py`

**Interfaces:**
- Produces:
  - `ALLOWED_FIELDS: tuple[str, ...]` (the nine field keys, in the order listed in Global Constraints).
  - `validate_args(args: dict) -> tuple[list[str], list[str]]`: returns `(scene_ids, fields)`; raises `ValueError` with a human-readable message.
  - `build_update_input(scene_id: str, fields: list[str]) -> dict`: a `SceneUpdateInput` with `id` plus only the ticked fields' empty values.
  - `run(stash, scene_ids: list[str], fields: list[str], log) -> tuple[int, list[str]]`: returns `(cleared_count, failed_scene_ids)`. `stash` needs `update_scene(dict)`; `log` needs `info`, `error`, `progress(float)`.
  - `main()`: entry point reading Stash's stdin JSON.

- [ ] **Step 1: Write the failing tests**

Create `tests/vhClearFields/test_vhClearFields.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest discover -s tests/vhClearFields -v`
Expected: FAIL/ERROR with `ModuleNotFoundError: No module named 'vhClearFields'`.

- [ ] **Step 3: Write the implementation**

Create `plugins/vhClearFields/vhClearFields.py`:

```python
import json
import sys

PLUGIN_ID = "vhClearFields"
TASK_MODE = "vhClearFields"

# field key -> (SceneUpdateInput key, factory for the empty value)
FIELD_CLEARS = {
    "title": ("title", str),
    "urls": ("urls", list),
    "date": ("date", lambda: None),
    "director": ("director", str),
    "performers": ("performer_ids", list),
    "studio": ("studio_id", lambda: None),
    "details": ("details", str),
    "stashIds": ("stash_ids", list),
    "code": ("code", str),
}
ALLOWED_FIELDS = tuple(FIELD_CLEARS)


def _as_list(args, key):
    value = args.get(key)
    if not isinstance(value, list):
        raise ValueError(f"'{key}' must be a list")
    return value


def validate_args(args):
    raw_ids = _as_list(args, "sceneIds")
    raw_fields = _as_list(args, "fields")

    scene_ids = []
    for raw in raw_ids:
        scene_id = str(raw)
        if not scene_id.isdigit():
            raise ValueError(f"invalid scene id: {scene_id!r}")
        if scene_id not in scene_ids:
            scene_ids.append(scene_id)

    unknown = [f for f in raw_fields if f not in FIELD_CLEARS]
    if unknown:
        raise ValueError(f"unknown field(s): {', '.join(map(str, unknown))}")

    fields = []
    for field in raw_fields:
        if field not in fields:
            fields.append(field)

    if not scene_ids:
        raise ValueError("no scenes given")
    if not fields:
        raise ValueError("no fields given")
    return scene_ids, fields


def build_update_input(scene_id, fields):
    update_input = {"id": scene_id}
    for field in fields:
        key, empty = FIELD_CLEARS[field]
        update_input[key] = empty()
    return update_input


def run(stash, scene_ids, fields, log):
    cleared = 0
    failed = []
    total = len(scene_ids)
    for index, scene_id in enumerate(scene_ids, start=1):
        try:
            stash.update_scene(build_update_input(scene_id, fields))
            cleared += 1
        except Exception as exc:
            failed.append(scene_id)
            log.error(f"{PLUGIN_ID}: scene {scene_id} failed: {exc}")
        log.progress(index / total)
    return cleared, failed


class Log:
    """Stash raw-plugin log protocol: level-prefixed lines on stderr."""

    @staticmethod
    def _emit(level, message):
        sys.stderr.write(f"\x01{level}\x02{message}\n")
        sys.stderr.flush()

    def info(self, message):
        self._emit("i", message)

    def error(self, message):
        self._emit("e", message)

    def progress(self, fraction):
        self._emit("p", fraction)


SCENE_UPDATE = "mutation SceneUpdate($input: SceneUpdateInput!) { sceneUpdate(input: $input) { id } }"


class StashClient:
    def __init__(self, connection):
        host = connection.get("Host") or "localhost"
        if host in ("0.0.0.0", "::"):
            host = "localhost"
        scheme = connection.get("Scheme") or "http"
        self.url = f"{scheme}://{host}:{connection.get('Port') or 9999}/graphql"
        cookie = connection.get("SessionCookie") or {}
        self.cookie = f"{cookie['Name']}={cookie['Value']}" if cookie.get("Name") else None

    def update_scene(self, update_input):
        body = json.dumps({"query": SCENE_UPDATE, "variables": {"input": update_input}})
        request = urllib.request.Request(
            self.url, data=body.encode(), headers={"Content-Type": "application/json"}
        )
        if self.cookie:
            request.add_header("Cookie", self.cookie)
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.load(response)
        if payload.get("errors"):
            raise RuntimeError("; ".join(e.get("message", "unknown error") for e in payload["errors"]))
        return payload["data"]["sceneUpdate"]


def main():
    log = Log()
    json_input = json.loads(sys.stdin.read())
    args = json_input.get("args", {})
    if args.get("mode") != TASK_MODE:
        log.error(f"{PLUGIN_ID}: unrecognised task mode; nothing to do")
        return

    try:
        scene_ids, fields = validate_args(args)
    except ValueError as exc:
        log.error(f"{PLUGIN_ID}: refusing to run: {exc}")
        return

    stash = StashClient(json_input["server_connection"])
    log.info(
        f"{PLUGIN_ID}: clearing {len(fields)} field(s) on {len(scene_ids)} scene(s)"
    )
    cleared, failed = run(stash, scene_ids, fields, log)

    log.info(f"{PLUGIN_ID}: cleared {cleared}, failed {len(failed)}")
    if failed:
        log.error(f"{PLUGIN_ID}: failed scene ids: {', '.join(failed)}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest discover -s tests/vhClearFields -v`
Expected: all tests PASS.

- [ ] **Step 5: Stage (commit only if the user has asked for commits)**

```bash
git add plugins/vhClearFields/vhClearFields.py tests/vhClearFields/test_vhClearFields.py
git diff --cached
```
If commits are wanted: `git commit -m "Add Clear Fields backend task"`.

---

### Task 2: Manifest, README and repo docs

**Files:**
- Create: `plugins/vhClearFields/vhClearFields.yml`
- Create: `plugins/vhClearFields/README.md`
- Modify: `CLAUDE.md` (plugin table)

**Interfaces:**
- Consumes: task name, `defaultArgs.mode`, setting keys from Global Constraints; script path `vhClearFields.py` (Task 1) and `vhClearFields.js`/`vhClearFields.css` (Task 3).
- Produces: a manifest the build script can package.

- [ ] **Step 1: Write the manifest**

Create `plugins/vhClearFields/vhClearFields.yml`:

```yaml
name: VH - Clear Fields
description: Bulk-clears chosen metadata fields on selected scenes from a Clear fields button on the scene list and scene page. Runs as a background task.
version: 1.0
ui:
  javascript:
    - vhClearFields.js
  css:
    - vhClearFields.css
exec:
  - python
  - "{pluginDir}/vhClearFields.py"
interface: raw
tasks:
  - name: Clear scene fields
    description: Clears the given fields on the given scenes. Started by the Clear fields button, not meant to be run by hand.
    defaultArgs:
      mode: vhClearFields
settings:
  clearTitle:
    displayName: Title
    description: Clear the title by default in the Clear fields dialog
    type: BOOLEAN
  clearUrls:
    displayName: URLs
    description: Clear the URLs by default in the Clear fields dialog
    type: BOOLEAN
  clearDate:
    displayName: Date
    description: Clear the date by default in the Clear fields dialog
    type: BOOLEAN
  clearDirector:
    displayName: Director
    description: Clear the director by default in the Clear fields dialog
    type: BOOLEAN
  clearPerformers:
    displayName: Performers
    description: Clear the performers by default in the Clear fields dialog
    type: BOOLEAN
  clearStudio:
    displayName: Studio
    description: Clear the studio by default in the Clear fields dialog
    type: BOOLEAN
  clearDetails:
    displayName: Details
    description: Clear the details by default in the Clear fields dialog
    type: BOOLEAN
  clearStashIds:
    displayName: Stash IDs
    description: Clear the stash IDs by default in the Clear fields dialog
    type: BOOLEAN
  clearCode:
    displayName: Studio code
    description: Clear the studio code by default in the Clear fields dialog
    type: BOOLEAN
```

- [ ] **Step 2: Write the README**

Create `plugins/vhClearFields/README.md`:

```markdown
# VH - Clear Fields

Bulk-clears chosen metadata fields on selected scenes, for scenes that Identify matched wrongly
when no correct match exists anywhere.

## Use

1. Select scenes in a scene list, or open a single scene and switch to its **Edit** tab.
2. Click **Clear fields…**. On the scene list the button appears once at least one scene is
   selected.
3. In the **Clear fields** dialog, tick the fields to clear under "Select the fields to clear." and
   click **OK**.
4. The second **Clear fields** dialog asks "Clear N fields on M scenes? This removes the following
   and cannot be undone." and lists the chosen fields. Click **Confirm**, or **Cancel** to go back
   to the field list with your ticks kept.
5. What happens next depends on where you started:
   - Scene page: the fields are cleared immediately and the page updates itself. A toast confirms.
   - Scene list: the work is queued as a background job (see Settings > Tasks) and a toast
     confirms it was queued. Refresh the page when the job finishes.

## Fields

Title, URLs (all), Date, Director, Performers (all), Studio, Details, Stash IDs (all), Studio
code. Cover, tags, groups, markers and generated files (sprites, previews) are never touched.
Only the ticked fields are changed. There is no undo.

## Settings

Settings > Plugins has one toggle per field, titled with the field name (for example "Studio
code"). Turning a toggle on clears that field by default in the Clear fields dialog, meaning its
box starts ticked. Stash plugin settings have no default value, so every toggle is off until you
turn it on; the dialog then starts with nothing ticked. The toggles only pre-tick boxes and never
clear anything on their own.

## Behaviour

- One `sceneUpdate` per scene. From the scene list, a scene that fails is logged with its ID and
  skipped; the rest continue, and the job log ends with a cleared/failed count. From the scene page
  an error is shown in a toast.
- The scene-list job refuses unknown field names, empty scene lists and empty field lists before
  any scene is touched.
- The background job uses only the Python standard library, so it does not need
  `PythonDepManager`, `stashapi` or git on the Stash host.

## Tests

`python3 -m unittest discover -s tests/vhClearFields` from the repository root. They cover the
field mapping and argument validation, the GraphQL client and log output against a local stub
server, the manifest, and that the UI file and the Python backend agree on field names, task name
and arguments. The dialogs and the Edit-tab behaviour have no automated tests; check them by hand
on a test Stash instance.

## Known limitations

- On the scene page the button shows only on the Edit tab. Stash keeps the active tab in page
  state rather than the URL, so the plugin detects it from the page and could break if Stash changes
  its tab markup.
- The button is a floating pill above the mobile bottom navigation bar, because the scene list
  toolbar and the scene page menu are not extension points in Stash's plugin API.
- On the scene list, cleared values are not shown until the page is refreshed.
```

- [ ] **Step 3: Add the plugin to the repo plugin table**

In `CLAUDE.md`, add this row after the `autoSetPerformerGender` row of the table under `## Plugins`:

```markdown
| `vhClearFields` | VH - Clear Fields | UI + Backend/task | Adds a "Clear fields..." button to the scene list (selected scenes) and scene page; a two-step dialog picks fields and confirms, then a background task clears the chosen fields (title, URLs, date, director, performers, studio, details, stash IDs, studio code) on every selected scene |
```

- [ ] **Step 4: Verify the build script packages it**

`vhClearFields.js` and `.css` do not exist yet, so create empty placeholders only for this check, then remove them:

```bash
touch plugins/vhClearFields/vhClearFields.js plugins/vhClearFields/vhClearFields.css
bash build_site.sh _site-check >/dev/null
grep -A8 "id: vhClearFields" _site-check/index.yml
unzip -l _site-check/vhClearFields.zip
rm plugins/vhClearFields/vhClearFields.js plugins/vhClearFields/vhClearFields.css
rm -rf _site-check   # repo-relative scratch dir; remove when done
```
Expected: an index entry with `name: VH - Clear Fields`, no `requires:`, and a zip containing `vhClearFields.yml`, `vhClearFields.py`, `README.md`.

- [ ] **Step 5: Stage (commit only if asked)**

```bash
git add plugins/vhClearFields/vhClearFields.yml plugins/vhClearFields/README.md CLAUDE.md
git diff --cached
```
If commits are wanted: `git commit -m "Add Clear Fields manifest and docs"`.

---

### Task 3: UI script

**Files:**
- Create: `plugins/vhClearFields/vhClearFields.js`
- Create: `plugins/vhClearFields/vhClearFields.css`

**Interfaces:**
- Consumes: task name `Clear scene fields`, `args_map` keys `sceneIds` / `fields`, field keys and setting keys (Global Constraints).
- Produces: `ClearFieldsButton({ sceneIds })` (renders nothing when `sceneIds` is empty) and two patches: `SceneList` (selection from `props.selectedIds`) and `ScenePage` (single scene from `props.scene.id`).

No automated test harness exists for UI plugins in this repo; verification is manual in Task 4. Keep logic thin: the pure rules live in the Python task.

- [ ] **Step 1: Write the script**

Create `plugins/vhClearFields/vhClearFields.js`:

```javascript
"use strict";
(() => {
  const api = window.PluginApi;
  const { React, patch, GQL, hooks, components, libraries } = api;
  const { useState } = React;
  const { Modal, Button, Form } = libraries.Bootstrap;
  const { useIntl } = libraries.Intl;
  const { faExclamationTriangle } = libraries.FontAwesomeSolid;
  const { Icon } = components;
  const h = React.createElement;

  const PLUGIN_ID = "vhClearFields";
  const TASK_NAME = "Clear scene fields";

  // input/empty mirror FIELD_CLEARS in vhClearFields.py (used for the synchronous scene-page path)
  const FIELDS = [
    { key: "title", setting: "clearTitle", label: "Title", input: "title", empty: () => "" },
    { key: "urls", setting: "clearUrls", label: "URLs", input: "urls", empty: () => [] },
    { key: "date", setting: "clearDate", label: "Date", input: "date", empty: () => null },
    { key: "director", setting: "clearDirector", label: "Director", input: "director", empty: () => "" },
    { key: "performers", setting: "clearPerformers", label: "Performers", input: "performer_ids", empty: () => [] },
    { key: "studio", setting: "clearStudio", label: "Studio", input: "studio_id", empty: () => null },
    { key: "details", setting: "clearDetails", label: "Details", input: "details", empty: () => "" },
    { key: "stashIds", setting: "clearStashIds", label: "Stash IDs", input: "stash_ids", empty: () => [] },
    { key: "code", setting: "clearCode", label: "Studio code", input: "code", empty: () => "" },
  ];

  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

  // Mirrors Stash's ModalComponent markup and classes so stock CSS applies.
  const StockModal = ({ show, cancelText, onCancel, accept, children }) =>
    h(
      Modal,
      { className: "ModalComponent vh-clear-fields-modal", keyboard: false, show, onHide: () => {} },
      h(Modal.Header, null, h(Icon, { icon: faExclamationTriangle }), h("span", null, "Clear fields")),
      h(Modal.Body, null, children),
      h(
        Modal.Footer,
        { className: "ModalFooter" },
        h("div"),
        h(
          "div",
          null,
          h(Button, { variant: "secondary", className: "ml-2", onClick: onCancel }, cancelText),
          h(
            Button,
            { variant: accept.variant, className: "ml-2", disabled: accept.disabled, onClick: accept.onClick },
            accept.text
          )
        )
      )
    );

  const ClearFieldsFlow = ({ sceneIds, defaults, sync, onClose }) => {
    const intl = useIntl();
    const Toast = hooks.useToast();
    const [runTask] = GQL.useRunPluginTaskMutation();
    const [updateScene] = GQL.useSceneUpdateMutation();
    const [step, setStep] = useState("pick");
    const [selected, setSelected] = useState(defaults);
    const [busy, setBusy] = useState(false);

    const cancelText = intl.formatMessage({ id: "actions.cancel" });
    const confirmText = intl.formatMessage({ id: "actions.confirm" });
    const summary = `${plural(selected.length, "field")} on ${plural(sceneIds.length, "scene")}`;

    const toggle = (key) =>
      setSelected((cur) => (cur.includes(key) ? cur.filter((k) => k !== key) : [...cur, key]));

    const onConfirm = async () => {
      setBusy(true);
      try {
        if (sync) {
          const input = { id: sceneIds[0] };
          FIELDS.filter((f) => selected.includes(f.key)).forEach((f) => {
            input[f.input] = f.empty();
          });
          await updateScene({ variables: { input } });
          Toast.success(`Cleared ${summary}`);
        } else {
          await runTask({
            variables: {
              plugin_id: PLUGIN_ID,
              task_name: TASK_NAME,
              description: `Clear ${summary}`,
              args_map: { sceneIds, fields: selected },
            },
          });
          Toast.success(`Queued: clearing ${summary}. Refresh the page when the task finishes.`);
        }
        onClose();
      } catch (e) {
        Toast.error(e);
        setBusy(false);
      }
    };

    if (step === "pick") {
      return h(
        StockModal,
        {
          show: true,
          cancelText,
          onCancel: onClose,
          accept: {
            variant: "primary",
            text: "OK",
            disabled: selected.length === 0,
            onClick: () => setStep("confirm"),
          },
        },
        h("p", null, "Select the fields to clear."),
        FIELDS.map((f) =>
          h(Form.Check, {
            key: f.key,
            type: "checkbox",
            id: `vh-clear-fields-${f.key}`,
            label: f.label,
            checked: selected.includes(f.key),
            onChange: () => toggle(f.key),
          })
        )
      );
    }

    return h(
      StockModal,
      {
        show: true,
        cancelText,
        onCancel: () => setStep("pick"),
        accept: { variant: "danger", text: confirmText, disabled: busy, onClick: onConfirm },
      },
      h("p", null, `Clear ${summary}? This removes the following and cannot be undone.`),
      h("ul", null, FIELDS.filter((f) => selected.includes(f.key)).map((f) => h("li", { key: f.key }, f.label)))
    );
  };

  // Scene page tabs are plain React state (no URL), so read the active tab from the DOM.
  const EDIT_TAB_SELECTOR =
    '[data-rb-event-key="scene-edit-panel"].active, [id$="-tabpane-scene-edit-panel"].active';

  const useEditTabActive = (enabled) => {
    const [active, setActive] = useState(false);
    React.useEffect(() => {
      if (!enabled) return undefined;
      const check = () => setActive(!!document.querySelector(EDIT_TAB_SELECTOR));
      check();
      const observer = new MutationObserver(check);
      observer.observe(document.body, {
        subtree: true,
        childList: true,
        attributes: true,
        attributeFilter: ["class"],
      });
      return () => observer.disconnect();
    }, [enabled]);
    return enabled ? active : true;
  };

  const ClearFieldsButton = ({ sceneIds, sync }) => {
    const { data } = GQL.useConfigurationQuery();
    const [open, setOpen] = useState(false);
    const tabVisible = useEditTabActive(!!sync);

    if (!sceneIds.length) return null;

    const plugins = (data && data.configuration && data.configuration.plugins) || {};
    const pluginSettings = plugins[PLUGIN_ID] || {};
    const defaults = FIELDS.filter((f) => pluginSettings[f.setting] === true).map((f) => f.key);

    return h(
      React.Fragment,
      null,
      tabVisible
        ? h(
            Button,
            { variant: "secondary", className: "vh-clear-fields-button", onClick: () => setOpen(true) },
            "Clear fields…"
          )
        : null,
      open ? h(ClearFieldsFlow, { sceneIds, defaults, sync, onClose: () => setOpen(false) }) : null
    );
  };

  patch.after("SceneList", function (props, _, result) {
    return h(
      React.Fragment,
      null,
      result,
      h(ClearFieldsButton, { sceneIds: Array.from(props.selectedIds || []) })
    );
  });

  patch.after("ScenePage", function (props, _, result) {
    return h(React.Fragment, null, result, h(ClearFieldsButton, { sceneIds: [props.scene.id], sync: true }));
  });
})();
```

- [ ] **Step 2: Write the stylesheet**

Create `plugins/vhClearFields/vhClearFields.css`:

```css
.vh-clear-fields-button {
  position: fixed;
  right: 24px;
  bottom: calc(80px + env(safe-area-inset-bottom, 0px));
  z-index: 1030;
  border-radius: 999px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4);
}

.vh-clear-fields-modal .modal-header {
  justify-content: flex-start;
  gap: 0.75rem;
}
```

- [ ] **Step 3: Syntax check**

Run: `node --check plugins/vhClearFields/vhClearFields.js`
Expected: no output (exit 0). If `node` is not installed, skip and rely on Task 4 (the browser console reports syntax errors at load).

- [ ] **Step 4: Stage (commit only if asked)**

```bash
git add plugins/vhClearFields/vhClearFields.js plugins/vhClearFields/vhClearFields.css
git diff --cached
```
If commits are wanted: `git commit -m "Add Clear Fields UI"`.

---

### Task 4: Verify on the test instance and settle UI placement

**Files:**
- Modify (if findings require): `plugins/vhClearFields/vhClearFields.js`, `plugins/vhClearFields/vhClearFields.css`
- Modify: `docs/superpowers/specs/2026-10-02-clear-fields-design.md` (align with what was built)

**Interfaces:**
- Consumes: Tasks 1-3 deliverables.
- Produces: confirmed behaviour, plus the spec updated so spec and plugin agree.

The test instance is the only Stash instance this plugin may be run against. Ask the user to put `plugins/vhClearFields/` into the test instance's plugins directory and click **Reload Plugins** in Settings > Plugins, or to tell you how else to deploy. Export its URL as `STASH_TEST_URL` for the GraphQL checks (add an API key header if the instance requires one).

- [ ] **Step 1: Confirm `sceneUpdate` clears each field (before any UI)**

For a throwaway scene on the test instance, populate all nine fields through the Stash UI, then send this mutation (replace `SCENE_ID`):

```bash
curl -sS "$STASH_TEST_URL/graphql" -H 'Content-Type: application/json' -d '{
  "query": "mutation($i: SceneUpdateInput!){ sceneUpdate(input:$i){ id title urls date director details code studio{id} performers{id} stash_ids{stash_id} } }",
  "variables": {"i": {"id":"SCENE_ID","title":"","urls":[],"date":null,"director":"","performer_ids":[],"studio_id":null,"details":"","stash_ids":[],"code":""}}
}'
```
Expected: `title`, `director`, `details`, `code` are `""`; `urls`, `performers`, `stash_ids` are `[]`; `date` and `studio` are `null`. If any field did not clear, stop and report which one; the design depends on this.

- [ ] **Step 2: Confirm the plugin loads and settings appear**

In Settings > Plugins: "VH - Clear Fields" is listed with nine toggles, all off. The browser console shows no errors from `vhClearFields.js`.

- [ ] **Step 3: Scene list flow**

1. Select two throwaway scenes with populated fields. Expected: a "Clear fields…" button appears (bottom right, clear of the mobile bottom navigation bar) only while scenes are selected.
2. Click it. Modal 1 "Select fields to clear" opens with nothing ticked; `OK` is disabled.
3. Tick Title and Studio, click `OK`. Modal 2 "Clear 2 fields on 2 scenes?" lists Title and Studio. `Cancel` returns to modal 1 with both still ticked.
4. `OK` then `Confirm`. Toast "Queued: clearing 2 fields on 2 scenes..." appears; the job appears in Settings > Tasks and completes; its log ends with "cleared 2, failed 0".
5. Refresh. Title and Studio are cleared on both scenes; every other field, the cover, tags, groups and markers are unchanged.

- [ ] **Step 4: Settings pre-tick**

Turn on the "Date" and "Director" settings in Settings > Plugins and save. Reopen the dialog (after a page refresh if needed). Expected: Date and Director are pre-ticked, nothing else.

- [ ] **Step 5: Scene page flow and look-and-feel**

Open a throwaway scene. Expected: the button appears; the dialog says "1 scene"; clearing works as in Step 3. Compare both modals with Stash's Delete dialog: header icon, spacing, button order (Cancel then accept, right-aligned) and colours should match. Note any visible difference.

- [ ] **Step 6: Edge cases**

- Unknown field: run the task from Settings > Tasks with no arguments. Expected: error log "refusing to run" and no scene changed.
- Failure isolation: not easily forced in the UI; covered by the unit test.
- Large selection: use list "Select all" on a filter matching a few hundred throwaway scenes; confirm the job shows progress and finishes.

- [ ] **Step 7: Fix findings**

If button placement overlaps other controls, adjust `vhClearFields.css` (e.g. `bottom`/`right`/`z-index`). If `patch.after("SceneList")` or `patch.after("ScenePage")` does not fire, or `props.selectedIds`/`props.scene` is absent in v0.31.x, report exactly what happens before choosing another approach; do not guess a different patch point.

- [ ] **Step 8: Align the spec with what was built**

Edit `docs/superpowers/specs/2026-10-02-clear-fields-design.md`:
- "Package layout": add `vhClearFields.css` (floating button styling).
- "UI flow" entry points: both entry points use a floating "Clear fields…" button (the list's selection toolbar and the scene page "⋯" menu are not patchable); list selection comes from `SceneList`'s `selectedIds`, the scene page from `ScenePage`'s `scene.id`.
- "Decisions and open items": mark list placement and detail-page menu as resolved (floating button), citing the test result from Step 3 and 5.

- [ ] **Step 9: Stage (commit only if asked)**

```bash
git add plugins/vhClearFields docs/superpowers/specs/2026-10-02-clear-fields-design.md
git diff --cached
```
If commits are wanted: `git commit -m "Verify Clear Fields on a test instance and update spec"`.
