# stash-plugins

Plugins for [Stash](https://github.com/stashapp/stash), published as a self-hosted source index via GitHub Pages. Two plugin flavors live here: **UI plugins** (client-side, patch the React frontend) and **backend/hook plugins** (server-side Python, triggered by Stash's post-mutation hooks).

**Source index URLs:** `https://visualhumanity.github.io/stash-plugins/main/index.yml` (releases) and `https://visualhumanity.github.io/stash-plugins/develop/index.yml` (pre-release builds from `develop`, for testing on a test Stash instance)

## Plugins

| Directory | Name | Type | Description |
|-----------|------|------|-------------|
| `flexibleDateInput` | Flexible Date Input | UI | Patches Stash's date input field with an "Attempt to fix?" helper that normalises a wide range of date formats (YYYYMMDD, MM-DD-YYYY, DD/MM/YYYY, epoch, etc.) into the required YYYY-MM-DD format |
| `autoSetPerformerGender` | Auto-set Performer Gender | Backend/hook | Sets a newly created performer's gender to a configured default if it doesn't already have one; fires on `Performer.Create.Post`, never overwrites an existing gender |
| `vhClearFields` | VH - Clear Fields | UI + Backend/task | Adds a "Clear fields..." button to the scene list (selected scenes) and scene page; a two-step dialog picks fields and confirms, then a background task clears the chosen fields (title, URLs, date, director, performers, studio, details, stash IDs, studio code) on every selected scene |
| `vhLinkTagsToPage` | VH - Link Tags To Page | UI | Tag links open the tag's detail page on the tab matching where the tag was clicked (scene to `/tags/<id>/scenes`, performer to `/tags/<id>/performers`, and so on) instead of a resource list with a tag filter; patches `TagLink` and replaces only its URL |

## Directory structure

UI plugins (JS/CSS):

```
plugins/
└── <PluginName>/
    ├── <PluginName>.yml    # plugin manifest
    ├── <PluginName>.js     # plugin script (see JavaScript conventions)
    ├── <PluginName>.css    # optional stylesheet
    └── README.md           # behavior, known limitations (flexibleDateInput predates this)
```

Backend/hook plugins (Python, run by Stash's plugin subprocess protocol):

```
plugins/
└── <PluginName>/
    ├── <PluginName>.yml    # plugin manifest (exec/interface/hooks/settings)
    ├── <PluginName>.py     # plugin script
    └── README.md           # settings, behavior, known limitations
```

The plugin ID (used in the published index, zip filename, and — for backend plugins — the
settings lookup key `config["plugins"][id]`) is derived from the `.yml` filename.

## YAML manifest

UI plugin:

```yaml
name: Human-readable Name
description: A short description shown in the Stash plugin list
version: 1.0.0                 # semantic version; combined with git hash for the published version
ui:
    javascript:
        - pluginName.js
    css:
        - pluginName.css      # omit if no stylesheet
    assets:
        /: .                  # serve all files in the directory as static assets
```

Backend/hook plugin:

```yaml
name: Human-readable Name
description: A short description shown in the Stash plugin list
version: 1.0.0
# requires: PythonDepManager   # optional comment, see Dependency Management below
exec:
  - python
  - "{pluginDir}/PluginName.py"
interface: raw
hooks:
  - name: Hook display name
    description: What this hook does
    triggeredBy:
      - Performer.Create.Post   # any TriggerEnum value stash supports, e.g. Scene.Update.Post
settings:
  settingKey:
    displayName: Shown in the UI
    description: Optional help text
    type: STRING                # BOOLEAN, NUMBER, or STRING only — no enum/dropdown type exists
```

- Unlike scrapers, plugins require `description:` and `version:` fields — both are used by the build script.
- `# requires:` is supported as an optional comment for declaring dependencies (see Dependency Management).
- Stash's plugin `settings:` schema has no `default` field — a setting is genuinely unset until
  a user saves a value on the Settings > Plugins page. Don't assume a fallback value exists
  unless the plugin script itself hardcodes one.

## JavaScript conventions

UI plugin JavaScript is **hand-written plain ES**, committed as-is: no TypeScript, no bundler, no build step (React via `React.createElement`). `vhClearFields` and `vhLinkTagsToPage` follow this. The exception is `flexibleDateInput.js`, which is esbuild output whose TypeScript source is not in this repo; edit it by hand with care, or rewrite it as plain ES.

Plugins interact with Stash through the Plugin API exposed on `window.PluginApi`:

```js
const { React, ReactDOM, patch } = window.PluginApi;

// Wrap an existing component
patch.after("ComponentName", (props, _, result) => {
    return React.createElement(React.Fragment, null, result, React.createElement(MyComponent, props));
});
```

Key API surface: `patch.before`, `patch.after`, `patch.instead` for component interception; standard React/ReactDOM for rendering.

## Python (backend/hook) conventions

Backend plugins are invoked by Stash as a subprocess, once per task run or per hook fire — not
long-running. The convention across the wider Stash plugin ecosystem (CommunityScripts,
feederbox826, etc.) is `stashapi` (the `stashapp-tools` PyPI package), not raw GraphQL calls:

```python
import json
import sys
from stashapi.stashapp import StashInterface
import stashapi.log as log

json_input = json.loads(sys.stdin.read())
stash = StashInterface(json_input["server_connection"])

config = stash.get_configuration()
settings = config.get("plugins", {}).get("<PluginName>", {})   # matches the .yml filename

args = json_input.get("args", {})
hook_context = args.get("hookContext")
if hook_context and hook_context["type"] == "Performer.Create.Post":
    performer = stash.find_performer(hook_context["id"], fragment="id gender")
    # ...
elif "mode" in args:
    ...   # manual task run, dispatch on args["mode"]
```

`json_input["args"]["hookContext"]` is only present when the script runs because of a
`triggeredBy` hook; `json_input["args"]["mode"]` is only present for a manually-run `tasks:`
entry. A plugin can support both in the same script.

This is a different execution model than the standalone maintenance scripts in
`stash-scrapers/tools/` (which read their own `config.ini` and run manually via `python
script.py`, outside of Stash entirely) — a backend plugin always receives its connection info
over stdin from Stash itself and should use `stashapi`, not `py_common.graphql`.

## Build and deployment

`build_site.sh` packages each plugin directory into a zip and writes `index.yml`. The GitHub Actions workflow (`.github/workflows/deploy.yml`) has four jobs: `refs` (pins the commits to test and build), `test` (unit tests), `build` and `deploy`.

- **Triggers:** PRs into `main` or `develop`, pushes to those branches, and manual runs. PRs and pushes only start the workflow when they touch `plugins/**`, `themes/**`, `build_site.sh`, `tests/**` or `.github/workflows/**`.
- **PRs:** `test` and `build` run against the PR's feature branch (its head commit). Nothing is deployed.
- **Pushes and manual runs:** a `refs` job pins the current `main` and `develop` tips. `test` runs once per pinned commit, and `build` builds the same commits into `_site/main` and `_site/develop`, so everything deployed has passed the tests. A Pages artifact deploy replaces the whole site, so both branches are always rebuilt together.
- **Deploy:** waits on `refs`, `test` and `build`, and runs only from `main` or `develop`. Because every deploy publishes both branches, a push deploys if either branch has changes under `plugins/`, `themes/`, `build_site.sh` or `.github/workflows/` since that branch's last successful push run; otherwise (for example a tests-only push) it is skipped. Manual runs always deploy. The `github-pages` environment allows deploys from `main` and `develop` only.
- **Queueing:** pushes and manual runs on `main` or `develop` share one concurrency group with `queue: max`, so they run one at a time in order and waiting runs are not cancelled. PR runs and manual runs on other branches never wait on it.

Published version format: `<yml-version>-<git-short-hash>` (e.g. `1.0.0-a3f9c12`).

### Artifact Structure

The Github Actions Workflow creates an artifact with the following structure:
```shell
.
└── DateFromFilename
    ├── DateFromFilename.py
    ├── DateFromFilename.yml
    └── manifest

2 directories, 3 files
```

The content of the manifest file is:
```shell
id: DateFromFilename
name: Extract Date from Filename
metadata: {}
version: 07d2aec
date: "2026-05-30 17:13:05"
requires: []
source_repository: https://visualhumanity.github.io/stash-scrapers/main/index.yml
files:
- DateFromFilename.yml
- DateFromFilename.py
```

## Adding a new plugin

UI plugin:

1. Create `plugins/<Name>/` with a `<Name>.yml`, a `<Name>.js` and a `README.md` (behavior, known limitations).
2. Write the JS as plain ES in an IIFE (see JavaScript conventions); there is no build step.
3. Follow the YAML conventions above (name, description, version, and ui sections are all required).
4. Merge to `main` — CI builds and publishes automatically.

Backend/hook plugin:

1. Create `plugins/<Name>/` with a `<Name>.yml` and `<Name>.py`, plus a `README.md` documenting
   settings and behavior.
2. Follow the YAML and Python conventions above — `exec`/`interface: raw`, a `hooks:` block with
   the relevant `triggeredBy` entries, and `# requires: PythonDepManager` if the script imports
   anything beyond the stdlib.
3. Merge to `main` — CI builds and publishes automatically.

## Dependency Management

Stash is deployed using a Docker image hosted in Docker Hub.  Since it is built by the developers of Stash, it is not sustainable to use multi-stage builds (e.g., a custom Dockerfile) to manage additional PIP packages.

This is why the Stash developers provide the `PythonDepManager` plugin, which allows community-maintained plugins to use dependencies that are not part of the base image. 

Documentation on how to use `PythonDepManager` is available here: `<CommunityScripts checkout>/plugins/PythonDepManager/README.md`.

Here is the plugin's docstring:
```py
"""
🐍 Simple dependency management for Python projects.

Automatically installs and manages dependencies in isolated folders.
Supports regular packages, git repositories, and version constraints.

Usage:
    Add a dependency to PythonDepManager into your plugin.yml file so it gets installed automatically:
    #requires: PythonDepManager

    Then, in your python code, you can use the "ensure_import" function to install and manage dependencies:
    # Example usage:
    from PythonDepManager import ensure_import

    ensure_import("requests==2.26.0")                                     # Specific version
    ensure_import("requests>=2.25.0")                                     # Minimum version
    ensure_import("bs4:beautifulsoup4==4.9.3")                            # Custom import name/Metapackage Imports
    ensure_import("stashapi@git+https://github.com/user/repo.git")        # Git repo
    ensure_import("stashapi@git+https://github.com/user/repo.git@main")   # Git branch/tag
    ensure_import("stashapi@git+https://github.com/user/repo.git@abc123") # Git commit
    ensure_import("bs4:beautifulsoup4==4.9.3", "requests==2.26.0") # Multiple packages

    # If you want to flush all dependencies, you can use the flush_dependencies function:
    from PythonDepManager import flush_dependencies
    flush_dependencies()
```
```

## Agent skills

### Issue tracker

Issues live in this repo's GitHub Issues, managed with the `gh` CLI using the visualhumanity token. See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
