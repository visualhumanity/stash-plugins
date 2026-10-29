# Every plugin has a README with a shared structure

Every plugin has a `README.md` in its own folder. A PR that adds a plugin or changes what it does adds or updates that README in the same PR. Where information lives (root README, folder README or `CLAUDE.md`) is set by [ADR 0001](0001-root-readme-role.md); this ADR covers what a folder README holds and in what order. A unit test fails when a plugin folder has no `README.md`.

The READMEs follow one structure, shared with scraper READMEs in stash-scrapers, so a reader finds the same thing in the same place in either repo. User-facing sections come first, maintainer material last. The anchor headings, in order:

- H1: the plugin's `name:` from its `.yml`.
- A description of 1-3 sentences.
- A `Requires:` line, only for dependencies beyond what every plugin gets. Link each one as specifically as possible: a relative link to its folder when it is in this repo, otherwise its folder in the external repo, otherwise the repo or project page.
- `## Features`: an unordered list of what the plugin does.
- Free sections specific to the plugin, such as how a hook behaves or how a task maps to a Stash feature.
- `## Configuration`, only when the plugin has settings.
- `## Known limitations`, optional.
- `## Development`: tests and internals, kept short.

Specific to plugins:

- "What every plugin gets" is what Stash itself installs for every plugin.
- Free sections go only between Features and Configuration.
- Configuration is a `Setting | Default | Description` table with one row per setting, named by the label shown on Settings > Plugins. No type or setting key columns. Stash stores no defaults, so the Default column says what the plugin does while a setting is unset.
- The `.yml` setting descriptions stay one-line hints and may state the default. Repeating the default in the README is accepted: both copies are in the same folder and change in the same PR.

Spelling is US, as in Stash. Field names, setting keys, action names and UI labels are quoted exactly as Stash or the code spells them.

When restructuring an existing README, move and trim its content rather than rewriting it. A "Behavior" section splits by audience: user-visible rules go to Features or a free section, failure cases to Known limitations, internals to Development.

All examples are synthetic (`Example Scene`, `/data/example/video.mp4`): no real titles, names, hosts or paths outside the repo.

This is guidance, not a template. Agents may add free sections, adjust wording and trim content without amending this ADR. Only a change to whether READMEs exist, where they live, when they are kept current, or the anchor headings needs a new ADR.

## Considered options

- No written rule: every plugin README had its own headings and settings format, and one plugin had none.
- A strict template with a heading linter: turns guidance into boilerplate, and plugins with no settings or limitations would carry empty headings.
- Settings tables with type and setting key columns: the key is not what a user sees on Settings > Plugins, and the type is clear from the control.
