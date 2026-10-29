# Auto-set Performer Gender

Sets a newly created performer's gender to a configured default, if the performer doesn't
already have a gender set.

Requires: [PythonDepManager](https://github.com/stashapp/CommunityScripts/tree/main/plugins/PythonDepManager), used to install `stashapp-tools` at runtime.

## Features

- Runs only when a performer is created (`Performer.Create.Post`), never on update, so it never
  runs against existing performers.
- Never overwrites a gender. If the performer already has one (however it got set: manual entry,
  a scraper, the create dialog, etc.), the plugin does nothing.
- Covers performers created through the normal path: manual creation, a scraper's "Create"
  action, the stash-box tagger, the Identify task, etc.

## Configuration

Set this once in **Settings > Plugins** and save. There is no other configuration: no per-gender
toggles, no conditional logic.

| Setting | Default | Description |
|---|---|---|
| Default gender | none (plugin does nothing) | One of `MALE`, `FEMALE`, `TRANSGENDER_MALE`, `TRANSGENDER_FEMALE`, `INTERSEX`, `NON_BINARY` (case-insensitive). Leave blank to disable the plugin. |

## Known limitations

- If **Default gender** is empty or doesn't match a valid gender, the plugin skips the performer
  and logs an error. There is no hardcoded fallback.
- Performers created as a side effect of a full library JSON import/restore (Settings > Tasks >
  Import) don't trigger `Performer.Create.Post`: Stash's importer writes those records directly
  rather than going through the `performerCreate` mutation, so the plugin does not set their
  gender.

## Development

`autoSetPerformerGender.py` handles the `Performer.Create.Post` hook with `stashapi`. There are no
tests.
