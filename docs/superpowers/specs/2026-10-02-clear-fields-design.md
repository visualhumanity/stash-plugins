# Clear Fields plugin: design

Date: 2026-10-02
Status: implemented; first manual round on the test instance done, review pending

## Problem

Stash's Identify task sometimes matches the wrong scene and fills in incorrect metadata. When a correct match exists it can be re-matched manually. When none exists (the scene is in no stash-box), each wrong value must be cleared by hand, scene by scene. That does not scale.

## Goal

From inside Stash, let the user select many scenes (or open a single scene) and bulk-clear a chosen set of fields. The tool is deliberately dumb: no matching logic, no detection of "wrong" scenes. The user filters and selects; the plugin clears.

## Why a plugin (not a scraper or external script)

Spike result (Stash v0.31.1 source, `internal/identify`): a scraper can only clear Title, Details, Director and Code, and only if the Identify field strategy is Overwrite. Date, URLs, performers, studio and stash IDs cannot be cleared via Identify: empty values are skipped or are no-ops. The scene-edit "scrape with" dialog is merge-only for the same reason. `sceneUpdate` accepts null/empty for every target field, so a plugin that calls it directly can clear all nine. A UI plugin gives the in-Stash, select-then-click workflow; a plugin task gives asynchronous execution through Stash's job queue.

## Scope

Clearable fields (all nine in scope):

| Field | `sceneUpdate` input value |
|---|---|
| Title | `title: ""` |
| URLs (all) | `urls: []` |
| Date | `date: null` |
| Director | `director: ""` |
| Performers (all) | `performer_ids: []` |
| Studio | `studio_id: null` |
| Details (description) | `details: ""` |
| Stash IDs (all) | `stash_ids: []` |
| Studio code | `code: ""` |

Never touched: cover, groups, tags, markers, and anything the Generate task produces (sprites, previews, etc.). Only the keys for ticked fields are sent, so unticked fields are left exactly as they are.

Not in scope: detecting misidentified scenes, undo, clearing images/galleries/performers/other entity types, auto-refreshing the page.

## Package layout

One hybrid plugin, `plugins/vhClearFields/`:

- `vhClearFields.yml`: manifest with `ui:`, `exec:`, `interface: raw`, one `tasks:` entry and nine `settings:` entries.
- `vhClearFields.js`: UI part (button, two modals, toast, task trigger).
- `vhClearFields.css`: styling for the floating "Clear fields…" button.
- `vhClearFields.py`: backend task (the actual clearing).
- `README.md`: settings, behaviour, limitations (per repo convention for backend plugins).

Add a row to the plugin table in the repo `CLAUDE.md` (type: UI + Backend/task).

## Settings

Nine BOOLEAN settings, one per field, shown under Settings > Plugins. Each setting's title is the field name (e.g. "Studio code") and its description is "Clear the <field> by default in the Clear fields dialog". Keys: `clearTitle`, `clearUrls`, `clearDate`, `clearDirector`, `clearPerformers`, `clearStudio`, `clearDetails`, `clearStashIds`, `clearCode`.

Stash plugin settings have no default value, so an unset toggle is off: out of the box nothing is pre-ticked. The user can enable the fields they want pre-ticked, or tick fields in the modal each time. The settings only pre-fill modal 1; they never cause clearing on their own. The UI reads them via the `configuration` GraphQL query (`plugins.vhClearFields`).

## UI flow

Entry points:

Both entry points use a floating "Clear fields…" button, because the list's selection toolbar and the scene page "⋯" menu are not patchable by plugins.

1. **Scene list**: while one or more scenes are selected, the button appears (selection read from `SceneList`'s `selectedIds`). "Select all" in Stash's list covers the whole filtered set.
2. **Scene detail page**: the button appears only while the Edit tab is active, with the current scene (from `ScenePage`'s `scene.id`). Same flow with one scene. Tab state is plain React state with no URL, so the plugin watches the DOM (`MutationObserver`) for the active `scene-edit-panel` tab link.

Flow:

1. User selects scenes and clicks "Clear fields…".
2. **Modal 1**, titled "Clear fields", with the text "Select the fields to clear." above nine checkboxes, pre-ticked from settings. Buttons: `Cancel` (secondary) and `OK` (primary), disabled while nothing is ticked.
3. `OK` closes modal 1 and opens **modal 2**, also titled "Clear fields", with the text "Clear F fields on N scenes? This removes the following and cannot be undone." above the list of chosen field names. Buttons: `Cancel` (secondary) and `Confirm` (danger). `Cancel` here returns to modal 1 with ticks preserved.
4. Dialog titles are left-aligned beside the warning icon. On the **scene page** (always one scene) `Confirm` runs `sceneUpdate` synchronously from the UI, so Stash's cache updates and the page shows the cleared values without a refresh; a toast confirms. On the **scene list** `Confirm` calls `runPluginTask` and shows a toast "Queued: clearing F fields on N scenes". The job appears in Settings > Tasks.
5. No auto-refresh for the list task. The user refreshes manually (an auto-refresh when the job finishes later could interrupt them unexpectedly).

Look and feel: Stash's `ModalComponent` is not exposed to plugins; `AlertModal` is, but its footer order differs from Stash's destructive dialogs. The plugin builds its modals from `react-bootstrap` (via `PluginApi.libraries.Bootstrap`) using the same markup and class names as `ModalComponent` (`ModalComponent`, `ModalFooter`), a warning-triangle header icon (`PluginApi.components.Icon` with the FontAwesome solid set), and Stash's own locale strings where they exist (`actions.cancel`, `actions.confirm`). Footer order: Cancel (secondary) then accept (primary, or danger on modal 2), right-aligned, matching the delete and auto-tag dialogs.

## Backend task

Used by the scene list only (the scene page clears synchronously from the UI, see UI flow). Manifest `tasks:` entry, e.g. "Clear scene fields", invoked by the UI through `runPluginTask(plugin_id, task_name, description, args_map)` with `args_map = { sceneIds: [...], fields: [...] }`.

`vhClearFields.py`:

- Stdlib only: no `PythonDepManager`/`stashapi` (PythonDepManager requires git on the host, absent from some Stash containers). Reads `server_connection` from stdin JSON, calls `sceneUpdate` through a small `urllib` GraphQL client, raw interface, logs through the raw-plugin stderr protocol. This deviates from the repo's `stashapi` convention on purpose.
- Validates `fields` against the nine allowed keys and refuses unknown ones. Refuses an empty `fields` or `sceneIds`.
- Builds one `SceneUpdateInput` per scene containing only `id` plus the ticked fields' empty values (mapping table above), and applies it with `sceneUpdate`.
- Reports progress, continues past a failing scene, logs each failure with the scene ID, and ends with a summary: cleared X, failed Y.
- Does not read plugin settings; the UI passes the final field list, so the task is explicit and reproducible.

## Error handling

- UI: if `runPluginTask` (list) or `sceneUpdate` (scene page) fails, show an error toast; nothing is queued or changed.
- Task: per-scene failure is logged and counted, never aborts the batch. A non-empty failure count is surfaced as an error-level log line so the job shows it.
- No partial-state rollback; an interrupted job leaves already-cleared scenes cleared.

## Testing

- Automated (stdlib `unittest`, no Stash needed): the field-to-input mapping and argument validation; the `urllib` GraphQL client, log output and `main()` against a local stub server; manifest checks; and contract checks that the UI file and the backend agree on the field table, plugin and task names, task arguments and dialog wording. The dialogs, the synchronous scene-page update and the Edit-tab detection are not automated (no JS test runner in the repo) and stay manual.
- Manual, on a dedicated test Stash instance only (never production): create scenes with all nine fields populated, run the flow from both entry points, and verify that exactly the ticked fields clear while cover, tags, groups, markers and generated files are unchanged; confirm the job appears in the queue and that the toast and counts are right; confirm settings pre-tick modal 1 and are off by default.
- Prototype check: where the buttons can be injected and that `sceneUpdate` clears every field. Reported as working in the first manual round on the test instance, together with the dialogs, queueing and settings.

## Decisions and open items

- **JS authoring (decided):** this repo tracks only compiled JS and has no TypeScript source or build step for it. This plugin's JS will be hand-written plain ES (React via `React.createElement`), committed as-is, with no build infrastructure added. Approved.
- **Button placement (decided):** floating pill button on both the list and the scene page, via `patch.after("SceneList")` and `patch.after("ScenePage")`, positioned 80px above the bottom (plus the safe-area inset) so it clears the mobile bottom navigation bar. On the scene page it shows only while the Edit tab is active. Both patches fire in v0.31.1 (confirmed on the test instance); the first placement at the bottom edge covered the mobile nav bar, hence the offset. The Edit-tab check depends on Stash's tab markup and is the part most likely to need rework after a Stash upgrade.
- **Stash version:** developed against Stash v0.31.1; the manifest does not pin a minimum version.
