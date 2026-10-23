"""VH - Identify Images: Identify-style bulk scraping for images.

Stash runs this script once per task run, passing the server connection and
task arguments as JSON on stdin. Log lines go to stderr in Stash's raw plugin
log format.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from identify_client import StashClient, image_path  # noqa: E402
from identify_rules import (  # noqa: E402
    build_update_input,
    describe_changes,
    describe_report,
    has_result,
    pending_creates,
    plan_changes,
)
from identify_settings import SettingsError, parse_settings  # noqa: E402

PLUGIN_ID = "vhIdentifyImages"
TASK_MODE = "identify"


class Log:
    """Stash raw-plugin log protocol: level-prefixed lines on stderr."""

    @staticmethod
    def _emit(level, message):
        sys.stderr.write(f"\x01{level}\x02{message}\n")
        sys.stderr.flush()

    def info(self, message):
        self._emit("i", f"{PLUGIN_ID}: {message}")

    def error(self, message):
        self._emit("e", f"{PLUGIN_ID}: {message}")

    def progress(self, fraction):
        self._emit("p", fraction)


class ScrapeFailed(Exception):
    pass


def scrape(stash, sources, image_id):
    """Try each source in order; return the first non-empty result, or None.

    Raises ScrapeFailed when no source gave a result and at least one errored.
    """
    errors = []
    for source in sources:
        try:
            results = stash.scrape_image(source, image_id)
        except Exception as exc:
            errors.append(f"{source}: {exc}")
            continue
        if results and has_result(results[0]):
            return results[0]
    if errors:
        raise ScrapeFailed("; ".join(errors))
    return None


class RunState:
    """What one run has done so far: outcome counts and entities created (or, in a dry run, planned)."""

    def __init__(self):
        self.counts = {"updated": 0, "unchanged": 0, "no result": 0, "failed": 0}
        self.created = {"performers": 0, "tags": 0}
        # creation key -> new ID (None in a dry run)
        self.created_ids = {}


SINGULAR = {"performers": "performer", "tags": "tag"}


def resolve_creates(stash, settings, changes, state, label, log):
    """Give every to-be-created performer or tag an ID, creating each name once per run."""
    for field, entry in pending_creates(changes):
        key = entry["key"]
        if key not in state.created_ids:
            if settings.dry_run:
                log.info(f"{label}: would create {SINGULAR[field]} {entry['name']!r}")
                state.created_ids[key] = None
            else:
                new_id = str(stash.create(field, entry["create"]))
                log.info(f"{label}: created {SINGULAR[field]} {entry['name']!r} (id {new_id})")
                state.created_ids[key] = new_id
            state.created[field] += 1
        entry["id"] = state.created_ids[key]

    if settings.dry_run:
        return
    # a reused ID may already be linked; drop duplicates and changes that came to nothing
    for field in ("performers", "tags"):
        if field not in changes:
            continue
        old, new = changes[field]
        unique = []
        for entry in new:
            if entry["id"] not in [e["id"] for e in unique]:
                unique.append(entry)
        if sorted(e["id"] for e in old) == sorted(e["id"] for e in unique):
            del changes[field]
        else:
            changes[field] = (old, unique)


def process_image(stash, settings, image_id, label, state, log):
    """Scrape and apply one image. Returns 'updated', 'unchanged' or 'no result'."""
    image = stash.find_image(image_id)
    scraped = scrape(stash, settings.sources, image_id)
    if scraped is None:
        log.info(f"{label}: no scrape result")
        return "no result"
    create_options = {
        "performers": settings.create_missing_performers,
        "tags": settings.create_missing_tags,
        "skip_single_name": settings.skip_single_name_performers,
    }
    changes, report = plan_changes(image, scraped, settings.field_strategies, create_options)
    if report:
        log.info(f"{label}: {describe_report(report)}")
    resolve_creates(stash, settings, changes, state, label, log)
    if not changes:
        return "unchanged"
    if settings.dry_run:
        log.info(f"{label}: would change {describe_changes(changes)}")
        return "updated"
    stash.update_image(build_update_input(image_id, changes))
    log.info(f"{label}: changed {describe_changes(changes)}")
    return "updated"


def run_task(stash, settings, log):
    images = stash.find_images(settings.folder_prefixes, settings.image_limit)
    mode = " (dry run, nothing is written)" if settings.dry_run else ""
    log.info(f"identifying {len(images)} image(s) with {', '.join(settings.sources)}{mode}")

    state = RunState()
    total = len(images)
    for index, (image_id, path) in enumerate(images, start=1):
        label = f"image {image_id} ({path})"
        try:
            outcome = process_image(stash, settings, image_id, label, state, log)
        except Exception as exc:
            outcome = "failed"
            log.error(f"{label} failed: {exc}")
        state.counts[outcome] += 1
        log.progress(index / total)

    counts, created = state.counts, state.created
    log.info(
        f"processed {total}, updated {counts['updated']}, unchanged {counts['unchanged']}, "
        f"no result {counts['no result']}, failed {counts['failed']}, "
        f"performers created {created['performers']}, tags created {created['tags']}{mode}"
    )
    return state


def main():
    log = Log()
    json_input = json.loads(sys.stdin.read())
    args = json_input.get("args") or {}
    if args.get("hookContext"):
        return
    if args.get("mode") != TASK_MODE:
        log.error("unrecognised task mode; nothing to do")
        return

    stash = StashClient(json_input.get("server_connection") or {})
    try:
        raw_settings = stash.plugin_settings(PLUGIN_ID)
    except Exception as exc:
        log.error(f"could not read plugin settings: {exc}")
        return
    try:
        settings = parse_settings(raw_settings)
    except SettingsError as exc:
        log.error(f"refusing to run, invalid settings: {exc}")
        return

    try:
        run_task(stash, settings, log)
    except Exception as exc:
        log.error(f"run stopped: {exc}")


if __name__ == "__main__":
    main()
