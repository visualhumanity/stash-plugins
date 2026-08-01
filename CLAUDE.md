# stash-plugins

Plugins for [Stash](https://github.com/stashapp/stash), published as a self-hosted source index via GitHub Pages. Two plugin flavors live here: **UI plugins** (client-side, patch the React frontend) and **backend/hook plugins** (server-side Python, triggered by Stash's post-mutation hooks).

**Source index URL:** `https://visualhumanity.github.io/stash-plugins/main/index.yml`

## Plugins

| Directory | Name | Type | Description |
|-----------|------|------|-------------|
| `flexibleDateInput` | Flexible Date Input | UI | Patches Stash's date input field with an "Attempt to fix?" helper that normalises a wide range of date formats (YYYYMMDD, MM-DD-YYYY, DD/MM/YYYY, epoch, etc.) into the required YYYY-MM-DD format |
| `autoSetPerformerGender` | Auto-set Performer Gender | Backend/hook | Sets a newly created performer's gender to a configured default if it doesn't already have one; fires on `Performer.Create.Post`, never overwrites an existing gender |

## Directory structure

UI plugins (compiled JS/CSS):

```
plugins/
└── <PluginName>/
    ├── <PluginName>.yml    # plugin manifest
    ├── <PluginName>.js     # bundled JavaScript (compiled from TypeScript source)
    └── <PluginName>.css    # optional stylesheet
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
version: 1.0                  # semantic version; combined with git hash for the published version
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
version: 1.0
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

The `.js` files are **compiled, bundled output** (built from TypeScript source with a bundler such as esbuild). Do not hand-edit the compiled output; edit the TypeScript source and rebuild.

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

`build_site.sh` packages each plugin directory into a zip and writes `index.yml`. The GitHub Actions workflow (`.github/workflows/deploy.yml`) triggers on pushes to **`main`** that touch `plugins/**`, `themes/**`, `build_site.sh`, or the workflow file itself, then deploys to GitHub Pages.

Published version format: `<yml-version>-<git-short-hash>` (e.g. `1.0-a3f9c12`).

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

1. Create `plugins/<Name>/` with at minimum a `<Name>.yml` and `<Name>.js`.
2. Build the JS from source before committing — only the compiled output is tracked.
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

Documentation on how to use `PythonDepManager` is available here: `D:\git\_stash\stashapp\CommunityScripts\plugins\PythonDepManager\README.md`.

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