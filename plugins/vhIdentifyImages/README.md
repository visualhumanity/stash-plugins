# VH - Identify Images

Does for images what Stash's Identify task does for scenes. A task goes through every image under the configured folders, runs an image scraper on each one (the same scrape as the image's Scrape menu), and applies the result using Identify's per-field ignore, merge and overwrite rules.

**Take a database backup before the first full run.** An overwrite option applied to thousands of images cannot be undone from the plugin. Try the settings first with **Dry run** on and a small **Image limit**.

## Running it

Settings > Tasks > Plugin Tasks > VH - Identify Images > **Identify images**. Progress shows in Stash's task list. Each changed image is logged (Settings > Logs) as field, old value and new value, and the run ends with a summary:

```
processed 120, updated 95, unchanged 20, no result 4, failed 1
```

- **updated**: at least one field changed (with Dry run on: would change).
- **unchanged**: the scraper returned a result, but no field needed changing. No update is sent.
- **no result**: the scraper returned nothing for the image. The image is skipped.
- **failed**: the scrape or the update gave an error. The error is logged with the image ID and path, and the run carries on with the next image.

Each scrape starts the scraper's own process, so a first run over a large library can take hours.

## Settings

Stash plugin settings have no stored defaults: an empty setting means the default below.

| Setting | Type | Default | Meaning |
|---|---|---|---|
| Scraper ID | text | `GalleryDlReddit` | ID of the image scraper to run. Use a scraper that appears in the image Scrape menu. |
| Folder prefixes | text | all images | Only images whose file path starts with one of these are processed. Separate several with `\|`, for example `/data/example/reddit/\|/data/example/twitter/`. Spaces around each entry are trimmed. The match is a plain "starts with", so end a folder with `/` to avoid also matching `/data/example/reddit2/`. |
| Title option | text | `merge` | `ignore`, `merge` or `overwrite` (any case). See field options. |
| Code option | text | `merge` | As above, for the studio code. |
| Details option | text | `merge` | As above, for details. |
| Date option | text | `merge` | As above, for the date. |
| Dry run | on/off | off | Compute and log every change without writing anything. |
| Image limit | number | 0 (no limit) | Stop after this many images, in path order. |

Every setting is checked before the run starts. An invalid value (for example a field option of `replace`, or a limit that is not a whole number) stops the run before anything is written, with an error naming the setting.

## Field options

These are Identify's rules for single-value fields:

| Option | Image field empty | Image field already set |
|---|---|---|
| `ignore` | left alone | left alone |
| `merge` | set to the scraped value | left alone |
| `overwrite` | set to the scraped value | replaced by the scraped value |

A field the scraper returns nothing for (missing or blank) is never touched, under any option. The image is updated only when at least one field changes.

## Mapping to Identify

| Identify | This plugin |
|---|---|
| Sources list | Scraper ID (one source for now; the task already goes through an ordered list and uses the first result) |
| Field options: Title, Code, Details, Date | Title, Code, Details, Date options |
| Default strategy for an unset field: merge | Same |
| Paths to process | Folder prefixes |

## Known limitations

- Only title, code, details and date are applied so far. URLs, studio, performers and tags from the scrape are not yet applied.
- Stash-box sources are not supported (Stash's single-image scrape has no stash-box support).
