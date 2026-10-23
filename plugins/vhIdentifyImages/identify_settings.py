"""Plugin settings: parsing, defaults and validation.

Stash stores no defaults for plugin settings, so every default lives here.
All values are checked before the plugin makes its first write.
"""

from dataclasses import dataclass

DEFAULT_SCRAPER_ID = "GalleryDlReddit"
PREFIX_SEPARATOR = "|"
FIELD_STRATEGIES = ("ignore", "merge", "overwrite")
DEFAULT_STRATEGY = "merge"

# field name -> setting key
FIELD_SETTINGS = {
    "title": "fieldTitle",
    "code": "fieldCode",
    "details": "fieldDetails",
    "date": "fieldDate",
    "urls": "fieldUrls",
    "performers": "fieldPerformers",
    "tags": "fieldTags",
    "studio": "fieldStudio",
}


class SettingsError(ValueError):
    pass


@dataclass(frozen=True)
class Settings:
    sources: tuple
    folder_prefixes: tuple
    field_strategies: dict
    create_missing_performers: bool
    create_missing_tags: bool
    create_missing_studios: bool
    skip_single_name_performers: bool
    set_organized: bool
    skip_organized: bool
    scrape_on_scan: bool
    dry_run: bool
    image_limit: int


def _scraper_id(raw, errors):
    value = raw.get("scraperId")
    if value is None:
        return DEFAULT_SCRAPER_ID
    if not isinstance(value, str):
        errors.append("scraperId must be text")
        return None
    return value.strip() or DEFAULT_SCRAPER_ID


def _folder_prefixes(raw, errors):
    value = raw.get("folderPrefixes")
    if value is None:
        return ()
    if not isinstance(value, str):
        errors.append("folderPrefixes must be text")
        return ()
    prefixes = []
    for part in value.split(PREFIX_SEPARATOR):
        part = part.strip()
        if part and part not in prefixes:
            prefixes.append(part)
    return tuple(prefixes)


def _field_strategies(raw, errors):
    strategies = {}
    for field, key in FIELD_SETTINGS.items():
        value = raw.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            strategies[field] = DEFAULT_STRATEGY
            continue
        normalised = value.strip().lower() if isinstance(value, str) else None
        if normalised not in FIELD_STRATEGIES:
            errors.append(f"{key} must be one of {', '.join(FIELD_STRATEGIES)}, got {value!r}")
            continue
        strategies[field] = normalised
    return strategies


def _boolean(raw, key, errors):
    value = raw.get(key)
    if value is None:
        return False
    if not isinstance(value, bool):
        errors.append(f"{key} must be on or off, got {value!r}")
        return False
    return value


def _image_limit(raw, errors):
    value = raw.get("imageLimit")
    if value is None or value == "":
        return 0
    number = None
    if isinstance(value, bool):
        number = None
    elif isinstance(value, int):
        number = value
    elif isinstance(value, float) and value.is_integer():
        number = int(value)
    elif isinstance(value, str) and value.strip().isdigit():
        number = int(value.strip())
    if number is None or number < 0:
        errors.append(f"imageLimit must be a whole number, 0 or more, got {value!r}")
        return 0
    return number


def parse_settings(raw):
    """Turn the stored plugin settings (or None) into Settings.

    Raises SettingsError naming every invalid setting.
    """
    raw = raw or {}
    errors = []
    settings = Settings(
        sources=(_scraper_id(raw, errors),),
        folder_prefixes=_folder_prefixes(raw, errors),
        field_strategies=_field_strategies(raw, errors),
        create_missing_performers=_boolean(raw, "createMissingPerformers", errors),
        create_missing_tags=_boolean(raw, "createMissingTags", errors),
        create_missing_studios=_boolean(raw, "createMissingStudios", errors),
        skip_single_name_performers=_boolean(raw, "skipSingleNamePerformers", errors),
        set_organized=_boolean(raw, "setOrganized", errors),
        skip_organized=_boolean(raw, "skipOrganized", errors),
        scrape_on_scan=_boolean(raw, "scrapeOnScan", errors),
        dry_run=_boolean(raw, "dryRun", errors),
        image_limit=_image_limit(raw, errors),
    )
    if errors:
        raise SettingsError("; ".join(errors))
    return settings
