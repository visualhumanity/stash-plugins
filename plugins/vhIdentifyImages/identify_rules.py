"""Field rules taken from Stash's Identify task, applied to one image.

Pure functions: the current image, a scrape result and the field strategies
give the planned changes. No Stash connection is needed.
"""

SINGLE_VALUE_FIELDS = ("title", "code", "details", "date")


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


def plan_changes(image, scraped, strategies):
    """Return {field: (old, new)} for every field the update would change."""
    changes = {}
    for field in SINGLE_VALUE_FIELDS:
        new = _scraped_text(scraped, field)
        if new is None:
            continue
        old = image.get(field)
        if old == new:
            continue
        if _should_set(strategies[field], bool(old)):
            changes[field] = (old, new)
    return changes


def build_update_input(image_id, changes):
    update = {"id": image_id}
    for field, (_old, new) in changes.items():
        update[field] = new
    return update


def describe_changes(changes):
    return ", ".join(f"{field}: {old!r} -> {new!r}" for field, (old, new) in changes.items())
