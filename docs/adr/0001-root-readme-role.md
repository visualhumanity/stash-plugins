# Root README is the human-facing index

The root `README.md` is the entry point for people who use or maintain this repo. It holds the production and develop index URLs, a table with one row per plugin or scraper and a 1-2 sentence description of each, and a short summary of the development process for human maintainers.

Detail about a single plugin or scraper lives in the `README.md` in its folder. `CLAUDE.md` repeats neither: it points agents to the root README for the index of what the repo contains, and to the folder READMEs for detail. A PR that adds, removes or renames a plugin or scraper, changes what it does, or changes a plugin's version also updates the root README table.

In stash-plugins the table has a version column copied from each plugin's `.yml`. In stash-scrapers it has none: a scraper's version is the git short hash of its last commit, which a README cannot hold without going stale on every change, so the source indexes are where to read it.

This is guidance, not a template. Agents may change headings, wording, columns and section order as the repo changes, without amending this ADR. Only a change to where information lives (root README, folder README or `CLAUDE.md`) needs a new ADR.

## Considered options

- Component list in `CLAUDE.md` only: human readers never see it.
- The same list in both `CLAUDE.md` and the README: the two drift apart.
