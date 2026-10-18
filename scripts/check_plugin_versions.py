#!/usr/bin/env python3
"""Fail when a PR changes a plugin without raising its version.

Usage: check_plugin_versions.py <target-ref> [--head <commit>]

<target-ref> is the branch the PR merges into, e.g. origin/develop or origin/main; its last
path component picks the new-plugin rule. Compares the plugins the feature branch changed
(three-dot diff, so only the branch's own changes) against the target ref's versions.
Exit codes: 0 all good, 1 version problems found, 2 usage or git error.
"""

import argparse
import os
import re
import subprocess
import sys

# SemVer 2.0 core only: no leading zeros, no pre-release or build tags
VERSION_RE = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")


def parse(version):
    match = VERSION_RE.fullmatch(version or "")
    return tuple(int(part) for part in match.groups()) if match else None


def is_exempt(path):
    """Docs that don't change how the plugin looks or behaves in Stash."""
    stem, ext = os.path.splitext(os.path.basename(path))
    return ext.lower() in (".md", ".txt") or stem.upper() in ("README", "CHANGELOG")


def changed_plugins(changed):
    """Plugin IDs with at least one non-exempt changed file inside plugins/<id>/."""
    ids = set()
    for path in changed:
        parts = path.split("/")
        if len(parts) >= 3 and parts[0] == "plugins" and not is_exempt(path):
            ids.add(parts[1])
    return sorted(ids)


def manifest(plugin_id):
    return f"plugins/{plugin_id}/{plugin_id}.yml"


def check(target, changed, base, head):
    """Return one failure line per changed plugin whose version breaks the rules.

    target: the branch the PR merges into, "develop" or "main".
    changed: repo-relative paths the feature branch changed (three-dot diff).
    base, head: plugin ID to version string on the target tip and the PR head. A plugin
    whose folder doesn't exist on that side is absent; one with no version line maps to None.
    """
    if target not in ("develop", "main"):
        raise ValueError(f"target must be develop or main, not {target!r}")
    failures = []
    for plugin_id in changed_plugins(changed):
        if plugin_id not in head:
            continue  # deleted (or renamed away)
        new = head[plugin_id]
        if new is None:
            failures.append(f"{plugin_id}: missing version in {manifest(plugin_id)}")
        elif parse(new) is None:
            failures.append(f"{plugin_id}: malformed version '{new}' in {manifest(plugin_id)} (expected X.Y.Z)")
        elif plugin_id not in base:
            failure = new_plugin_failure(target, new)
            if failure:
                failures.append(f"{plugin_id}: {failure}")
        else:
            old = base[plugin_id]
            if parse(old) is None:
                failures.append(f"{plugin_id}: base version '{old}' on {target} is not X.Y.Z, cannot compare")
            elif parse(new) == parse(old):
                failures.append(f"{plugin_id}: version {new} not bumped (base {old})")
            elif parse(new) < parse(old):
                failures.append(f"{plugin_id}: version {new} is lower than base {old}")
    return failures


def new_plugin_failure(target, version):
    """New plugins start at 0.1.0 on develop and are promoted to exactly 1.0.0 on main."""
    if target == "develop" and not (0, 1, 0) <= parse(version) < (1, 0, 0):
        return f"new plugin on develop must be 0.Y.Z, at least 0.1.0 (got {version})"
    if target == "main" and parse(version) != (1, 0, 0):
        return f"new plugin on main must be 1.0.0 (got {version})"
    return None


def read_version(text):
    """The manifest's first "version:" line, read the way build_site.sh reads it."""
    for line in text.splitlines():
        if line.startswith("version:"):
            value = line.split(" ", 1)[1] if " " in line else ""
            value = value.rstrip("\r")
            if len(value) >= 2 and value[0] == value[-1] == '"':
                value = value[1:-1]
            return value
    return None


def git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def versions_at(commit, plugin_ids):
    versions = {}
    for plugin_id in plugin_ids:
        if not git("ls-tree", "-d", "--name-only", commit, f"plugins/{plugin_id}").strip():
            continue  # folder doesn't exist at this commit
        try:
            versions[plugin_id] = read_version(git("show", f"{commit}:{manifest(plugin_id)}"))
        except subprocess.CalledProcessError:
            versions[plugin_id] = None  # folder without a manifest
    return versions


def main(argv=None):
    parser = argparse.ArgumentParser(description="Fail when a changed plugin's version wasn't bumped.")
    parser.add_argument("target", help="branch the PR merges into, e.g. origin/develop")
    parser.add_argument("--head", default="HEAD", help="feature branch commit (default: HEAD)")
    args = parser.parse_args(argv)
    target_name = args.target.rsplit("/", 1)[-1]
    try:
        # --no-renames: a renamed plugin folder is a deletion plus a new plugin.
        # -z: NUL-separated and unquoted, so paths with spaces or non-ASCII characters survive.
        diff = git("diff", "-z", "--name-only", "--no-renames", f"{args.target}...{args.head}")
        changed = [path for path in diff.split("\0") if path]
        plugin_ids = changed_plugins(changed)
        failures = check(
            target=target_name,
            changed=changed,
            base=versions_at(args.target, plugin_ids),
            head=versions_at(args.head, plugin_ids),
        )
    except subprocess.CalledProcessError as error:
        print(f"git failed: {' '.join(error.cmd)}\n{error.stderr.strip()}", file=sys.stderr)
        return 2
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    for failure in failures:
        print(failure)
    if failures:
        return 1
    print(f"Plugin versions OK against {args.target} ({len(plugin_ids)} changed plugin(s)).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
