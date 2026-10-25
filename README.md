# Stash Plugins

Plugins for [Stash](https://github.com/stashapp/stash), published as source indexes you can add to your Stash instance.

## Install

| Index | Branch | URL |
|---|---|---|
| Production | `main` | [https://visualhumanity.github.io/stash-plugins/main/index.yml](https://visualhumanity.github.io/stash-plugins/main/index.yml) |
| Develop | `develop` | [https://visualhumanity.github.io/stash-plugins/develop/index.yml](https://visualhumanity.github.io/stash-plugins/develop/index.yml) |

In Stash, go to **Settings > Plugins**, click **Add Source** and paste the production index URL. The develop index holds pre-release builds for testing.

## Plugins

| Plugin | Description | Version |
|---|---|---|
| [Auto-set Performer Gender](plugins/autoSetPerformerGender/) | Sets a newly created performer's gender to a configured default. Never overwrites an existing gender. | 1.0.0 |
| [Flexible Date Input](plugins/flexibleDateInput/) | Adds an "Attempt to fix?" helper to date fields that converts common date formats to `YYYY-MM-DD`. | 1.0.0 |
| [VH - Clear Fields](plugins/vhClearFields/) | Bulk-clears chosen metadata fields on selected scenes, from a "Clear fields" button on the scene list and scene page. | 1.0.0 |
| [VH - Identify Images](plugins/vhIdentifyImages/) | Identify for images: scrapes images under chosen folders with an image scraper and applies the results with Identify's ignore, merge and overwrite rules. | 1.0.1 |
| [VH - Link Tags To Page](plugins/vhLinkTagsToPage/) | Makes tag links open the tag's page on the tab matching where you clicked, instead of a filtered list. | 1.0.0 |
| [VH - Player Aspect Ratio Fix](plugins/vhPlayerAspectRatioFix/) | Adds a button to the scene player that stretches the picture to 16:9, 4:3 or 1:1. Playback only: files and metadata are not changed. | 1.0.0 |

Versions are those on the branch you are viewing.

## Development

- `develop` is the integration branch. Every push publishes the develop index, for testing on a test Stash instance.
- `main` is the release branch. It publishes the production index.
- Flow: feature branch, PR into `develop`, install from the develop index and test, then a release PR from `develop` into `main`.
- Every push to either branch rebuilds and republishes both indexes.
- A PR that changes a plugin bumps its version once; CI checks this. New plugins start at `0.1.0` and get `1.0.0` in the release PR that first brings them to `main`.
- Full rules for agents and maintainers: [`CLAUDE.md`](CLAUDE.md).

## License

[AGPL-3.0](LICENCE)
