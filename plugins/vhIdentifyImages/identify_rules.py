"""Field rules taken from Stash's Identify task, applied to one image.

Pure functions: the current image, a scrape result and the field strategies
give the planned changes. No Stash connection is needed.
"""

SINGLE_VALUE_FIELDS = ("title", "code", "details", "date")
# relationship field -> ImageUpdateInput key
RELATIONSHIP_FIELDS = {"performers": "performer_ids", "tags": "tag_ids"}


def _scraped_text(scraped, field):
    value = scraped.get(field)
    if isinstance(value, str) and value.strip():
        return value
    return None


def has_result(scraped):
    """True when the scrape result holds at least one value."""
    if not scraped:
        return False
    for value in scraped.values():
        if isinstance(value, str) and value.strip():
            return True
        if isinstance(value, (list, dict)) and value:
            return True
    return False


def _should_set(strategy, has_existing):
    if strategy == "ignore":
        return False
    return not has_existing or strategy == "overwrite"


def _append_unique(values, additions):
    result = list(values)
    for value in additions:
        if value not in result:
            result.append(value)
    return result


def _single_value_changes(image, scraped, strategies, changes):
    for field in SINGLE_VALUE_FIELDS:
        new = _scraped_text(scraped, field)
        if new is None:
            continue
        old = image.get(field)
        if old == new:
            continue
        if _should_set(strategies[field], bool(old)):
            changes[field] = (old, new)


def _url_changes(image, scraped, strategy, changes):
    new_urls = [u for u in scraped.get("urls") or [] if isinstance(u, str) and u.strip()]
    if not new_urls or strategy == "ignore":
        return
    old = list(image.get("urls") or [])
    if strategy == "overwrite":
        # Identify overwrites only when a scraped URL is not already present
        if any(url not in old for url in new_urls):
            changes["urls"] = (old, _append_unique([], new_urls))
    else:
        merged = _append_unique(old, new_urls)
        if len(merged) != len(old):
            changes["urls"] = (old, merged)


def _text(value):
    return value.strip() if isinstance(value, str) else ""


def creation_key(field, create_input):
    """Key for reusing a created entity within a run.

    Names compare case-insensitively, as Stash matches them; a performer's
    disambiguation is part of its identity.
    """
    key = (field, create_input["name"].lower())
    if field == "performers":
        key += (create_input.get("disambiguation", "").lower(),)
    return key


def _create_input(field, item):
    """Create input for a scraped item with no stored ID, or None when it has no name."""
    name = _text(item.get("name"))
    if not name:
        return None
    create_input = {"name": name}
    if field == "performers":
        disambiguation = _text(item.get("disambiguation"))
        if disambiguation:
            create_input["disambiguation"] = disambiguation
        urls = [u for u in item.get("urls") or [] if _text(u)]
        if urls:
            create_input["urls"] = urls
    return create_input


def _is_single_name(create_input):
    # Identify's rule: no space in the name and no disambiguation
    return " " not in create_input["name"] and not create_input.get("disambiguation")


def _relationship_changes(image, scraped, field, strategy, options, changes, report):
    items = scraped.get(field) or []
    if not items or strategy == "ignore":
        return
    old = [{"id": str(e["id"]), "name": e.get("name")} for e in image.get(field) or []]
    new = list(old) if strategy == "merge" else []
    for item in items:
        stored_id = item.get("stored_id")
        if stored_id is not None:
            if str(stored_id) not in [e["id"] for e in new]:
                new.append({"id": str(stored_id), "name": item.get("name")})
            continue
        create_input = _create_input(field, item) if options.get(field) else None
        if create_input is None:
            report.setdefault("unmatched", {}).setdefault(field, []).append(item.get("name"))
            continue
        if field == "performers" and options.get("skip_single_name") and _is_single_name(create_input):
            report.setdefault("skipped_single_name", []).append(create_input["name"])
            continue
        key = creation_key(field, create_input)
        if key not in [e.get("key") for e in new]:
            new.append({"id": None, "name": create_input["name"], "key": key, "create": create_input})
    if any(e["id"] is None for e in new) or sorted(e["id"] for e in old) != sorted(e["id"] for e in new):
        changes[field] = (old, new)


def plan_changes(image, scraped, strategies, create_options=None):
    """Plan one image's update.

    create_options: {"performers": bool, "tags": bool, "skip_single_name": bool}.

    Returns (changes, report). changes maps field -> (old, new) for every
    field the update would change. Performer and tag lists hold
    {"id", "name"} entries; an entry still to be created has id None plus
    "key" and "create" (the create input). report lists scraped items that
    are not linked: "unmatched" (per field) and "skipped_single_name".
    """
    create_options = create_options or {}
    changes, report = {}, {}
    _single_value_changes(image, scraped, strategies, changes)
    _url_changes(image, scraped, strategies["urls"], changes)
    for field in RELATIONSHIP_FIELDS:
        _relationship_changes(image, scraped, field, strategies[field], create_options, changes, report)
    return changes, report


def pending_creates(changes):
    """Entries in the planned changes that still need creating, as (field, entry)."""
    return [
        (field, entry)
        for field in RELATIONSHIP_FIELDS
        if field in changes
        for entry in changes[field][1]
        if entry["id"] is None
    ]


def build_update_input(image_id, changes):
    update = {"id": image_id}
    for field, (_old, new) in changes.items():
        if field in RELATIONSHIP_FIELDS:
            update[RELATIONSHIP_FIELDS[field]] = [entry["id"] for entry in new]
        else:
            update[field] = new
    return update


def _display(field, value):
    if field in RELATIONSHIP_FIELDS:
        return repr([e["name"] if e.get("name") else f"id {e['id']}" for e in value])
    return repr(value)


def describe_changes(changes):
    return ", ".join(
        f"{field}: {_display(field, old)} -> {_display(field, new)}" for field, (old, new) in changes.items()
    )


def describe_report(report):
    parts = []
    for field, names in report.get("unmatched", {}).items():
        parts.append(f"not linked, no existing match: {field}: {names!r}")
    if report.get("skipped_single_name"):
        parts.append(f"skipped single-name performers: {report['skipped_single_name']!r}")
    return "; ".join(parts)
