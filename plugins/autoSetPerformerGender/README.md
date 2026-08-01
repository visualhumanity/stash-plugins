# Auto-set Performer Gender

Sets a newly created performer's gender to a configured default, if the performer doesn't
already have a gender set.

## Behavior

- Fires only on `Performer.Create.Post` — never on update, so it never runs against existing
  performers.
- If the performer already has a gender (however it got set — manual entry, a scraper, the
  create dialog, etc.), the plugin does nothing. Gender is never overwritten.
- If the performer has no gender, the plugin reads the **Default gender** setting below. If
  that setting is empty or doesn't match a valid gender, the plugin skips the performer and
  logs an error — there is no hardcoded fallback.

## Settings

| Setting | Type | Description |
|---|---|---|
| Default gender | String | One of `MALE`, `FEMALE`, `TRANSGENDER_MALE`, `TRANSGENDER_FEMALE`, `INTERSEX`, `NON_BINARY` (case-insensitive). Leave blank to disable the plugin entirely — it ships with no default and does nothing until this is set. |

There is no other configuration — no per-gender toggles, no conditional logic. Set this once
in **Settings > Plugins** and save.

## Known limitation

Performers created as a side effect of a full library JSON import/restore (Settings > Tasks >
Import) don't trigger `Performer.Create.Post` — Stash's importer writes those records directly
rather than going through the `performerCreate` mutation. This plugin only covers performers
created through the normal path: manual creation, a scraper's "Create" action, the stash-box
tagger, the Identify task, etc.

## Dependencies

Requires the [PythonDepManager](https://github.com/stashapp/CommunityScripts/tree/main/plugins/PythonDepManager)
plugin to be installed — it's declared as a dependency and used to install `stashapp-tools` at
runtime.
