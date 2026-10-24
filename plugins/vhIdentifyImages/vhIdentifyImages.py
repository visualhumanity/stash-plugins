"""VH - Identify Images: Identify-style bulk scraping for images.

Stash runs this script once per task run, passing the server connection and
task arguments as JSON on stdin. Log lines go to stderr in Stash's raw plugin
log format.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from identify_client import StashClient, Unauthorized, image_path  # noqa: E402
from identify_rules import (  # noqa: E402
    abbreviate,
    add_organized,
    build_update_input,
    fold_case,
    describe_changes,
    describe_report,
    has_result,
    pending_creates,
    plan_changes,
    studio_create_input,
    studio_key,
    studio_name,
    studio_update_input,
)
from identify_settings import SettingsError, parse_settings  # noqa: E402

PLUGIN_ID = "vhIdentifyImages"
TASK_MODE = "identify"
HOOK_TYPE = "Image.Create.Post"


# Stash reads plugin stderr with a line scanner that gives up on lines over 64 KiB
MAX_LINE_BYTES = 60000


def _cap(line):
    data = line.encode("utf-8")
    if len(data) <= MAX_LINE_BYTES:
        return line
    kept = data[:MAX_LINE_BYTES].decode("utf-8", errors="ignore")
    return f"{kept} ... (truncated, {len(data)} bytes)"


class Log:
    """Stash raw-plugin log protocol: level-prefixed lines on stderr.

    Every line of a message gets its own prefix and is kept under Stash's
    line limit. If Stash stops reading, logging goes quiet instead of
    crashing the run.
    """

    closed = False

    @classmethod
    def _emit(cls, level, message):
        if cls.closed:
            return
        try:
            for line in str(message).splitlines() or [""]:
                sys.stderr.write(f"\x01{level}\x02{_cap(line)}\n")
            sys.stderr.flush()
        except (BrokenPipeError, OSError, ValueError):
            cls.closed = True
            # keep the interpreter's own final flush from failing too
            sys.stderr = open(os.devnull, "w")

    def info(self, message):
        self._emit("i", f"{PLUGIN_ID}: {message}")

    def debug(self, message):
        self._emit("d", f"{PLUGIN_ID}: {message}")

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
        except Unauthorized:
            raise
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
        self.created = {"performers": 0, "tags": 0, "studio": 0}
        # creation key -> new ID (None in a dry run)
        self.created_ids = {}
        # IDs of existing parent studios already written to in this run
        self.updated_parents = set()
        # creates and studio updates sent so far
        self.writes = 0
        # studio key -> (existing ID, how it matched) or (None, None), from name and alias lookups
        self.studio_lookups = {}


SINGULAR = {"performers": "performer", "tags": "tag", "studio": "studio"}


def _same_entity(field, entity, create_input):
    if fold_case(entity.get("name") or "") != fold_case(create_input["name"]):
        return False
    if field == "performers":
        return fold_case(entity.get("disambiguation") or "") == fold_case(create_input.get("disambiguation") or "")
    return True


def find_existing(stash, field, create_input):
    """The one existing performer, tag or studio for a name, as (entity, matched_by), or (None, None).

    Looks up by name, then (tags and studios) by alias, the way Stash matches
    scraped names. Stash's EQUALS is SQL LIKE, so results are compared again
    here: exact name, ASCII case ignored, same disambiguation for performers.
    """
    found = [e for e in stash.find_by_name(field, create_input["name"]) if _same_entity(field, e, create_input)]
    if len(found) == 1:
        return found[0], "name"
    if found or field == "performers":
        return None, None
    wanted = fold_case(create_input["name"])
    found = [
        e
        for e in stash.find_by_name(field, create_input["name"], attribute="aliases")
        if any(fold_case(alias) == wanted for alias in e.get("aliases") or [])
    ]
    if len(found) == 1:
        return found[0], "alias"
    return None, None


def create_or_link(stash, field, create_input, label, log):
    """Create a performer, tag or studio; return (id, created).

    When the create fails because the name already exists, or is another
    tag's or studio's alias (a parallel scan hook or another client created
    it after the scrape), link that one instead, if exactly one matches.
    Otherwise the create error is raised.
    """
    try:
        new_id = str(stash.create(field, create_input))
        return new_id, True
    except RuntimeError as exc:
        if "already exists" not in str(exc) and "is used as alias for" not in str(exc):
            raise
        entity, _matched_by = find_existing(stash, field, create_input)
        if entity is None:
            raise
        log.info(f"{label}: linked existing {SINGULAR[field]} {entity['name']!r} (id {entity['id']}) after a name clash")
        return str(entity["id"]), False


def resolve_creates(stash, settings, changes, state, label, log):
    """Give every to-be-created performer or tag an ID, creating each name once per run."""
    for field, entry in pending_creates(changes):
        key = entry["key"]
        if key not in state.created_ids:
            if settings.dry_run:
                log.info(f"{label}: would create {SINGULAR[field]} {entry['name']!r}")
                state.created_ids[key] = None
                state.created[field] += 1
            else:
                new_id, created = create_or_link(stash, field, entry["create"], label, log)
                state.writes += 1
                if created:
                    log.info(f"{label}: created {SINGULAR[field]} {entry['name']!r} (id {new_id})")
                    state.created[field] += 1
                state.created_ids[key] = new_id
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


def _create_studio(stash, settings, item, parent_id, state, label, log):
    """Create a scraped studio once per run; return its ID (None in a dry run)."""
    key = studio_key(studio_name(item))
    if key not in state.created_ids:
        create_input = studio_create_input(item, parent_id)
        if settings.dry_run:
            log.info(f"{label}: would create studio {create_input['name']!r}")
            state.created_ids[key] = None
            state.created["studio"] += 1
        else:
            new_id, created = create_or_link(stash, "studio", create_input, label, log)
            state.writes += 1
            if created:
                log.info(f"{label}: created studio {create_input['name']!r} (id {new_id})")
                state.created["studio"] += 1
            state.created_ids[key] = new_id
    return state.created_ids[key]


def _existing_studio(stash, item, state):
    """Find a scraped studio in Stash by name, then alias, once per run.

    Stash matches a scraped image's studio but not its parent, so the parent
    (and its own parent) must be looked up here. Returns (id, matched_by) or
    (None, None).
    """
    if item.get("stored_id") is not None:
        return str(item["stored_id"]), "stored_id"
    key = studio_key(studio_name(item))
    if key not in state.studio_lookups:
        entity, matched_by = find_existing(stash, "studio", {"name": studio_name(item)})
        state.studio_lookups[key] = (str(entity["id"]), matched_by) if entity else (None, None)
    return state.studio_lookups[key]


def _apply_parent(stash, settings, parent, state, label, log):
    """Identify's parent handling for a studio about to be created; return the parent ID.

    A parent that exists gets the scraped parent's fields written to it; a
    missing one is created. Its own parent is only linked when it exists.
    """
    if not studio_name(parent):
        return None
    key = studio_key(studio_name(parent))
    if key in state.created_ids:
        return state.created_ids[key]
    grandparent = parent.get("parent")
    grandparent_id = _existing_studio(stash, grandparent, state)[0] if studio_name(grandparent) else None
    parent_id, matched_by = _existing_studio(stash, parent, state)
    if parent_id is None:
        return _create_studio(stash, settings, parent, grandparent_id, state, label, log)
    update = studio_update_input(dict(parent, stored_id=parent_id))
    if grandparent_id:
        update["parent_id"] = grandparent_id
    if matched_by == "alias":
        # the scraped name is this studio's alias; writing it as the name would clash
        update.pop("name")
    if update["id"] not in state.updated_parents:
        fields = abbreviate({k: v for k, v in update.items() if k != "id"})
        shown = f"{update['id']} ({studio_name(parent)!r})"
        if not fields:
            pass
        elif settings.dry_run:
            log.info(f"{label}: would update studio {shown} with {fields!r}")
        else:
            stash.update_studio(update)
            state.writes += 1
            log.info(f"{label}: updated studio {shown} with {fields!r}")
        state.updated_parents.add(update["id"])
    return update["id"]


def resolve_studio(stash, settings, changes, state, label, log):
    """Give a to-be-created studio an ID, handling its parent first, as Identify does."""
    if "studio" not in changes:
        return
    old, new = changes["studio"]
    if new["id"] is not None:
        return
    if new["key"] not in state.created_ids:
        parent_id = _apply_parent(stash, settings, new["create"].get("parent"), state, label, log)
        _create_studio(stash, settings, new["create"], parent_id, state, label, log)
    new["id"] = state.created_ids[new["key"]]
    if not settings.dry_run and old is not None and old["id"] == new["id"]:
        del changes["studio"]


def image_label(image_id, path):
    return f"image {image_id} ({path or 'no file'})"


def plan_image(stash, settings, image_id, scraped, state, label, log):
    """Read the image as it is now, plan its changes and make any creates they need."""
    image = stash.find_image(image_id)
    create_options = {
        "performers": settings.create_missing_performers,
        "tags": settings.create_missing_tags,
        "studio": settings.create_missing_studios,
        "skip_single_name": settings.skip_single_name_performers,
    }
    changes, report = plan_changes(image, scraped, settings.field_strategies, create_options)
    label = label or image_label(image_id, image_path(image))
    resolve_studio(stash, settings, changes, state, label, log)
    resolve_creates(stash, settings, changes, state, label, log)
    return image, changes, report, label


def process_image(stash, settings, image_id, label, state, log):
    """Scrape and apply one image. Returns 'updated', 'unchanged' or 'no result'.

    The image is read after the scrape, and read again after any creates,
    so the plan uses its current values and edits made in the meantime are
    not overwritten.
    """
    scraped = scrape(stash, settings.sources, image_id)
    if scraped is None:
        log.info(f"{label or f'image {image_id}'}: no scrape result")
        return "no result"
    writes = state.writes
    image, changes, report, label = plan_image(stash, settings, image_id, scraped, state, label, log)
    if report:
        log.info(f"{label}: {describe_report(report)}")
    if state.writes != writes:
        # creates take time; plan again from a fresh read (created IDs come from the run cache)
        image, changes, _report, label = plan_image(stash, settings, image_id, scraped, state, label, log)
    if settings.set_organized:
        add_organized(image, changes)
    if not changes:
        return "unchanged"
    if settings.dry_run:
        log.info(f"{label}: would change {describe_changes(changes)}")
        return "updated"
    stash.update_image(build_update_input(image_id, changes, settings.field_strategies))
    log.info(f"{label}: changed {describe_changes(changes)}")
    return "updated"


def check_sources(stash, sources):
    """Return an error naming scraperId when a source cannot scrape an existing image, else None."""
    scrapers = stash.image_scrapers()
    for source in sources:
        if source not in scrapers:
            return f"scraperId: no image scraper with ID {source!r} is installed"
        if "FRAGMENT" not in scrapers[source]:
            return f"scraperId: scraper {source!r} cannot scrape an existing image (it has no imageByFragment)"
    return None


def run_task(stash, settings, log):
    images = stash.find_images(settings.folder_prefixes, settings.image_limit, settings.skip_organized)
    mode = " (dry run, nothing is written)" if settings.dry_run else ""
    log.info(f"identifying {len(images)} image(s) with {', '.join(settings.sources)}{mode}")

    state = RunState()
    total = len(images)
    processed = 0
    for index, (image_id, path) in enumerate(images, start=1):
        label = image_label(image_id, path)
        try:
            outcome = process_image(stash, settings, image_id, label, state, log)
        except Unauthorized as exc:
            log.error(str(exc))
            break
        except Exception as exc:
            outcome = "failed"
            log.error(f"{label} failed: {exc}")
        state.counts[outcome] += 1
        processed += 1
        log.progress(index / total)

    counts, created = state.counts, state.created
    not_processed = f", not processed {total - processed}" if processed < total else ""
    log.info(
        f"processed {processed}, updated {counts['updated']}, unchanged {counts['unchanged']}, "
        f"no result {counts['no result']}, failed {counts['failed']}{not_processed}, "
        f"performers created {created['performers']}, tags created {created['tags']}, "
        f"studios created {created['studio']}{mode}"
    )
    return state


def run_hook(stash, settings, image_id, log):
    """Scan hook: run one new image through the same filters and steps as the task."""
    if settings.folder_prefixes or settings.skip_organized:
        eligible = stash.find_images(settings.folder_prefixes, 0, settings.skip_organized, image_id=image_id)
        if not eligible:
            log.debug(f"image {image_id}: outside the folder prefixes or organized; skipped")
            return
    problem = check_sources(stash, settings.sources)
    if problem:
        log.error(f"refusing to run, invalid settings: {problem}")
        return
    try:
        process_image(stash, settings, image_id, None, RunState(), log)
    except Exception as exc:
        log.error(f"image {image_id} failed: {exc}")


def load_settings(stash, log):
    try:
        raw_settings = stash.plugin_settings(PLUGIN_ID)
    except Exception as exc:
        log.error(f"could not read plugin settings: {exc}")
        return None, None
    try:
        return raw_settings, parse_settings(raw_settings)
    except SettingsError as exc:
        return raw_settings, exc


def main():
    log = Log()
    json_input = json.loads(sys.stdin.read())
    args = json_input.get("args") or {}
    hook = args.get("hookContext")
    if hook:
        # Only new images; the plugin's own updates fire Image.Update.Post
        if hook.get("type") != HOOK_TYPE or hook.get("id") is None:
            return
    elif args.get("mode") != TASK_MODE:
        log.error("unrecognised task mode; nothing to do")
        return

    stash = StashClient(json_input.get("server_connection") or {})
    raw_settings, settings = load_settings(stash, log)
    if hook and (raw_settings or {}).get("scrapeOnScan") is not True:
        # off: a scan fires this for every new image, so stay quiet and cheap
        return
    if settings is None:
        return
    if isinstance(settings, SettingsError):
        log.error(f"refusing to run, invalid settings: {settings}")
        return

    if hook:
        try:
            run_hook(stash, settings, str(hook["id"]), log)
        except Exception as exc:
            log.error(f"image {hook['id']} failed: {exc}")
        return

    try:
        problem = check_sources(stash, settings.sources)
    except Exception as exc:
        log.error(f"could not list scrapers: {exc}")
        return
    if problem:
        log.error(f"refusing to run, invalid settings: {problem}")
        return

    try:
        run_task(stash, settings, log)
    except Exception as exc:
        log.error(f"run stopped: {exc}")


if __name__ == "__main__":
    main()
