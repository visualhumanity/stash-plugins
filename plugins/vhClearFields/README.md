# VH - Clear Fields

Bulk-clears chosen metadata fields on selected scenes, for scenes that Identify matched wrongly
when no correct match exists anywhere.

## Features

- **Clear fields…** button on the scene list (once at least one scene is selected) and on a
  scene's **Edit** tab.
- Clears any of Title, URLs (all), Date, Director, Performers (all), Studio, Details, Stash IDs
  (all) and Studio code. Only the ticked fields are changed.
- Cover, tags, groups, markers and generated files (sprites, previews) are never touched.
- A confirmation dialog lists the chosen fields before anything is cleared. There is no undo.

## Use

1. Select scenes in a scene list, or open a single scene and switch to its **Edit** tab.
2. Click **Clear fields…**.
3. In the **Clear fields** dialog, tick the fields to clear under "Select the fields to clear." and
   click **OK**.
4. The second **Clear fields** dialog asks "Clear N fields on M scenes? This removes the following
   and cannot be undone." and lists the chosen fields. Click **Confirm**, or **Cancel** to go back
   to the field list with your ticks kept.
5. What happens next depends on where you started:
   - Scene page: the fields are cleared immediately and the page updates itself. A toast confirms.
   - Scene list: the work is queued as a background job (see Settings > Tasks) and a toast
     confirms it was queued. Refresh the page when the job finishes. The job log ends with a
     cleared/failed count.

## Configuration

Settings > Plugins > VH - Clear Fields has one toggle per field. Turning a toggle on makes that
field's box start ticked in the Clear fields dialog. The toggles only pre-tick boxes and never
clear anything on their own.

| Setting | Default | Description |
|---|---|---|
| Title | off | Start with Title ticked. |
| URLs | off | Start with URLs ticked. |
| Date | off | Start with Date ticked. |
| Director | off | Start with Director ticked. |
| Performers | off | Start with Performers ticked. |
| Studio | off | Start with Studio ticked. |
| Details | off | Start with Details ticked. |
| Stash IDs | off | Start with Stash IDs ticked. |
| Studio code | off | Start with Studio code ticked. |

## Known limitations

- From the scene list, a scene that fails is logged with its ID and skipped; the rest continue.
  From the scene page, an error is shown in a toast.
- On the scene page the button shows only on the Edit tab. Stash keeps the active tab in page
  state rather than the URL, so the plugin detects it from the page and could break if Stash changes
  its tab markup.
- The button is a floating pill above the mobile bottom navigation bar, because the scene list
  toolbar and the scene page menu are not extension points in Stash's plugin API.
- On the scene list, cleared values are not shown until the page is refreshed.

## Development

- One `sceneUpdate` per scene. The scene-list job refuses unknown field names, empty scene lists
  and empty field lists before any scene is touched.
- The background job uses only the Python standard library, so it does not need
  `PythonDepManager`, `stashapi` or git on the Stash host.
- Tests: `python3 -m unittest discover -t . -s tests/vhClearFields` from the repo root. They cover
  the field mapping and argument validation, the GraphQL client and log output against a local stub
  server, the manifest, and that the UI file and the Python backend agree on field names, task name
  and arguments. The dialogs and the Edit-tab behavior have no automated tests; check them by hand
  on a test Stash instance.
