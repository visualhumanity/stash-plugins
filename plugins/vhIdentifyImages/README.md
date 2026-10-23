# VH - Identify Images

Does for images what Stash's Identify task does for scenes. A task goes through every image under the configured folders, runs an image scraper on each one (the same scrape as the image's Scrape menu), and applies the result using Identify's per-field ignore, merge and overwrite rules. An optional scan hook does the same for each new image as Stash's scan finds it.

**Take a database backup before the first full run.** An overwrite option applied to thousands of images cannot be undone from the plugin. Try the settings first with **Dry run** on and a small **Image limit**.

## Running it

Settings > Tasks > Plugin Tasks > VH - Identify Images > **Identify images**. Progress shows in Stash's task list. Each changed image is logged (Settings > Logs) as field, old value and new value, and the run ends with a summary:

```
processed 120, updated 95, unchanged 20, no result 4, failed 1, performers created 3, tags created 0, studios created 2
```

- **updated**: at least one field changed (with Dry run on: would change).
- **unchanged**: the scraper returned a result, but no field needed changing. No update is sent.
- **no result**: the scraper returned nothing for the image. The image is skipped.
- **failed**: the scrape or the update gave an error. The error is logged with the image ID and path, and the run carries on with the next image.

Each scrape starts the scraper's own process, so a first run over a large library can take hours.

## Scrape on scan

With **Scrape on scan** on, each new image that a scan adds is scraped and applied right away, exactly as the task would handle it: same scraper, folder prefixes, skip organized, dry run, field options and create options. An image outside the folder prefixes (or organized, with Skip organized images on) is left alone.

It is off by default. Stash runs the plugin once for every new image a scan adds, and waits for it before going on, and each scrape also starts the scraper's own process. Turning it on before the first bulk run would make that first scan of a large library much slower. Run the **Identify images** task first, then turn Scrape on scan on so later downloads are handled as they are scanned. While it is off, each new image only costs the plugin reading its settings.

The plugin's own image updates fire Stash's `Image.Update.Post` hook, not `Image.Create.Post`, so the plugin never triggers itself.

## Settings

Stash plugin settings have no stored defaults: an empty setting means the default below.

| Setting | Type | Default | Meaning |
|---|---|---|---|
| Scraper ID | text | `GalleryDlReddit` | ID of the image scraper to run. It must be installed and able to scrape an existing image (an `imageByFragment` scraper, the kind the image Scrape menu uses); the run stops before touching any image if it is not. |
| Folder prefixes | text | all images | Only images whose file path starts with one of these are processed. Images with no file are only processed when this is empty. Separate several with `\|`, for example `/data/example/reddit/\|/data/example/twitter/`. Spaces around each entry are trimmed. The match is a plain "starts with", so end a folder with `/` to avoid also matching `/data/example/reddit2/`. |
| Title option | text | `merge` | `ignore`, `merge` or `overwrite` (any case). See field options. |
| Code option | text | `merge` | As above, for the studio code. |
| Details option | text | `merge` | As above, for details. |
| Date option | text | `merge` | As above, for the date. |
| URLs option | text | `merge` | As above, for URLs. See list fields. |
| Performers option | text | `merge` | As above, for performers. See list fields. |
| Tags option | text | `merge` | As above, for tags. See list fields. |
| Studio option | text | `merge` | As above, for the studio. See studio. |
| Create missing performers | on/off | off | Create scraped performers that are not in Stash yet, then link them. See creating missing performers and tags. |
| Create missing tags | on/off | off | Create scraped tags that are not in Stash yet, then link them. |
| Create missing studios | on/off | off | Create a scraped studio that is not in Stash yet (and its parent), then link it. See studio. |
| Skip single-name performers | on/off | off | Do not create a performer whose name has no space and who has no disambiguation. |
| Set organized | on/off | off | Also mark an image organized when it is updated. See organized. |
| Skip organized images | on/off | off | Leave organized images out of the run, so reruns skip finished images. They do not count toward the image limit. |
| Scrape on scan | on/off | off | Scrape each new image as Stash's scan finds it. See scrape on scan. |
| Dry run | on/off | off | Compute and log every change without writing anything. |
| Image limit | number | 0 (no limit) | Stop after this many images, in path order. |

Every setting is checked before the run starts, including that the scraper ID names an installed image scraper. An invalid value (for example a field option of `replace`, or a limit that is not a whole number) stops the run before anything is written, with an error naming the setting.

## Field options

These are Identify's rules for single-value fields:

| Option | Image field empty | Image field already set |
|---|---|---|
| `ignore` | left alone | left alone |
| `merge` | set to the scraped value | left alone |
| `overwrite` | set to the scraped value | replaced by the scraped value |

A field the scraper returns nothing for (missing or blank) is never touched, under any option. The image is updated only when at least one field changes.

### List fields: URLs, performers and tags

| Option | Effect |
|---|---|
| `ignore` | left alone |
| `merge` | scraped items are added to the image's existing ones, without duplicates |
| `overwrite` | the image's list is replaced by the scraped one |

- An empty scraped list changes nothing, under any option.
- URLs under `overwrite`: as in Identify, the list is replaced only when the scrape has a URL the image does not have yet.
- Performers and tags that Stash matched to an existing performer or tag (the same matching the image Scrape menu shows) are linked. Existing performers and tags are never edited.
- Unmatched items are created and linked when the matching create option is on (see below). Otherwise they are dropped and logged as "not linked, no existing match".
- Performers and tags under `overwrite`: as in Identify, the links are replaced by the matched and created items only. If none of the scraped performers match and none are created (or all are skipped), the image's performers are kept as they are. Same for tags.

### Creating missing performers and tags

- A created performer gets the scraped name, disambiguation (when the scraper gives one) and URLs. A created tag gets the scraped name.
- Each missing name is created once per run and reused for every later image that has it. Names compare ignoring ASCII case (A to Z only), as Stash matches them, so `Example` and `EXAMPLE` are one name but `É` and `é` differ. Two performers with the same name and different disambiguations are different performers.
- A scraped performer or tag without a name is never created.
- If a create fails, the image is counted as failed and the run carries on.
- The end summary adds `performers created` and `tags created`. With Dry run on, these count what would be created, and each would-be create is logged.
- **Skip single-name performers** follows Identify's rule: with it on, a performer whose name has no space and who has no disambiguation is not created (the rest of the image is still updated). Reddit uploader names such as `u_example_user` have no space, so keep this off when scraping Reddit images, or no uploader is ever created.

### Studio

The studio follows the single-value rule: `merge` sets it only when the image has no studio, `overwrite` replaces it, `ignore` leaves it. A scrape with no studio (or a blank name) changes nothing.

- A scraped studio that Stash matched to an existing studio is linked. That studio is never edited, and neither is its parent.
- With **Create missing studios** off, an unmatched studio is dropped and logged as "not linked, no existing match".
- With it on, an unmatched studio is created and linked, following Identify:
  - The new studio gets the scraped name, URLs, details and aliases, whichever the scraper returned.
  - If the scraped parent is missing too, the parent is created first, and the new studio is created under it.
  - If the scraped parent matched an existing studio, **that parent gets the scraped parent's fields written to it**: name, URLs (replacing its list), details and aliases, plus its own parent when the scrape names a matched one. Only fields the scraper returned are sent, so nothing is cleared. The name is always sent, so this can rename the parent, for example to a different letter case (`reddit` becomes `Reddit`). This is what Identify does. Each parent is written at most once per run.
- Each missing studio (and parent) is created once per run and reused. Names compare ignoring ASCII case, as for performers and tags.
- The end summary adds `studios created`, counting parents too. With Dry run on, it counts what would be created, and the log shows each would-be create and parent update.

### Organized

- **Set organized**: an image the plugin updates also gets marked organized, in the same update. An image already organized is not changed again. Dry run logs it as `organized: False -> True`.
- Difference from Identify: Identify's Set organized marks every scene it gets a scrape result for, even when nothing else changes. This plugin marks only images it actually updates; an image with no other change is not touched.
- **Skip organized images**: organized images are filtered out when the run lists images, before any scrape, so the image limit counts only images that will be processed. Combine both options to work through a library in batches.

## Mapping to Identify

| Identify | This plugin |
|---|---|
| Sources list | Scraper ID (one source for now; the task already goes through an ordered list and uses the first result) |
| Field options: Title, Code, Details, Date, URLs, Studio, Performers, Tags | Title, Code, Details, Date, URLs, Studio, Performers, Tags options |
| Create missing (performers, tags, studio) | Create missing performers, Create missing tags, Create missing studios |
| Skip single-name performers | Same (the "skipped" tag option is not supported) |
| Set organized | Same, but only for images that change (see organized) |
| Default strategy for an unset field: merge | Same |
| Paths to process | Folder prefixes |
| (no equivalent; Identify can run after a scan as a separate task) | Scrape on scan |

## Known limitations

- Studio and parent images (logos) from the scrape are not set.
- Stash-box sources are not supported (Stash's single-image scrape has no stash-box support).
