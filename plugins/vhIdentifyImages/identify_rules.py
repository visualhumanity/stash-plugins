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


def _relationship_changes(image, scraped, field, strategy, changes, unmatched):
    items = scraped.get(field) or []
    if not items or strategy == "ignore":
        return
    old = [(str(e["id"]), e.get("name")) for e in image.get(field) or []]
    new = list(old) if strategy == "merge" else []
    for item in items:
        stored_id = item.get("stored_id")
        if stored_id is None:
            unmatched.setdefault(field, []).append(item.get("name"))
            continue
        if str(stored_id) not in [entity_id for entity_id, _name in new]:
            new.append((str(stored_id), item.get("name")))
    if sorted(i for i, _ in old) != sorted(i for i, _ in new):
        changes[field] = (old, new)


def plan_changes(image, scraped, strategies):
    """Plan one image's update.

    Returns (changes, unmatched): changes maps field -> (old, new) for every
    field the update would change; unmatched maps performers/tags to the names
    of scraped items with no stored ID, which are dropped.
    """
    changes, unmatched = {}, {}
    _single_value_changes(image, scraped, strategies, changes)
    _url_changes(image, scraped, strategies["urls"], changes)
    for field in RELATIONSHIP_FIELDS:
        _relationship_changes(image, scraped, field, strategies[field], changes, unmatched)
    return changes, unmatched


def build_update_input(image_id, changes):
    update = {"id": image_id}
    for field, (_old, new) in changes.items():
        if field in RELATIONSHIP_FIELDS:
            update[RELATIONSHIP_FIELDS[field]] = [entity_id for entity_id, _name in new]
        else:
            update[field] = new
    return update


def _display(field, value):
    if field in RELATIONSHIP_FIELDS:
        return repr([name if name else f"id {entity_id}" for entity_id, name in value])
    return repr(value)


def describe_changes(changes):
    return ", ".join(
        f"{field}: {_display(field, old)} -> {_display(field, new)}" for field, (old, new) in changes.items()
    )


def describe_unmatched(unmatched):
    return ", ".join(f"{field}: {names!r}" for field, names in unmatched.items())
