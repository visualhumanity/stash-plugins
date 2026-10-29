# VH - Link Tags To Page

Makes tag links open the tag's detail page instead of a resource list with a tag filter. The tab
that opens matches where the tag was clicked.

## Features

- Tag links on cards and pages open the tag's page, on the tab for where you clicked (see Tabs).
- Only the link changes. The hover popover, hierarchy icon, middle-click and open in new tab work
  as before.
- Parent and child tag links on a tag's own page already open the tag page and are not changed.
- The tag page's "Include sub-tag content" switch still starts from your Stash interface setting.
- There are no settings. To get Stash's filtered-list links back, disable the plugin.

## Tabs

| Tag clicked on | Opens |
|---|---|
| Scene card, scene page, scene tagger, duplicate checker | `/tags/<id>/scenes` |
| Image card, image page | `/tags/<id>/images` |
| Gallery card, gallery page | `/tags/<id>/galleries` |
| Group card, group page | `/tags/<id>/groups` |
| Scene marker card (tag popover) | `/tags/<id>/markers` |
| Performer card, performer page | `/tags/<id>/performers` |
| Studio card, studio page | `/tags/<id>/studios` |

A tag shown anywhere else keeps Stash's default link.

## Known limitations

- Developed against Stash v0.31.1. If a Stash upgrade restructures `TagLink`, the patch stops
  applying and tag links fall back to Stash's filtered lists. Nothing breaks, but check this
  first after upgrading.
- Tag links not drawn by `TagLink` (filter sidebars, tag selectors in edit forms) are not changed.

## Development

Stash draws every tag chip with its `TagLink` component, which is told where the chip is shown.
The plugin patches `TagLink` with `patch.after` and swaps only the URL on the element Stash
returns. A chip shown somewhere the plugin does not recognize keeps Stash's default link.

There are no automated tests. Check by hand on a test Stash instance: for each place in the Tabs
table, hover a tag chip, check the link is `/tags/<id>/<tab>`, and click it.
