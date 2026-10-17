# Issue tracker: GitHub

Issues and PRDs for this repo live as GitHub issues in `visualhumanity/stash-plugins`. Use the `gh` CLI for all operations.

## Authentication: pin the visualhumanity token on every call

`gh` on the development machine may be logged in to more than one GitHub account, and the active account can change at any time. Never rely on it.

- Every `gh` call sets the token and the repo explicitly:

  ```bash
  GH_TOKEN=$(gh auth token --user visualhumanity) gh <command> --repo visualhumanity/stash-plugins ...
  ```

- For several calls in one shell command, `export GH_TOKEN=$(gh auth token --user visualhumanity)` first, then check that `gh api user --jq .login` prints `visualhumanity` before any write.
- Never call bare `gh`, and never run `gh auth switch`, `gh auth login` or `gh auth logout`.
- If `gh auth token --user visualhumanity` fails, stop and tell the user. Do not fall back to the active account.

The examples below assume `GH_TOKEN` is already exported as above.

## Public content

This repo and its issues are public. Issue titles, bodies, comments and labels follow the same rules as commits: no absolute paths outside the repo, hostnames, IP addresses, real usernames, media titles or other real data from a Stash instance. Use synthetic examples (`Example Scene`, `/data/example/video.mp4`, `192.0.2.1`).

## Conventions

- **Create an issue**: `gh issue create --repo visualhumanity/stash-plugins --title "..." --body "..."`. Use a heredoc for multi-line bodies.
- **Read an issue**: `gh issue view <number> --repo visualhumanity/stash-plugins --comments`, filtering comments by `jq` and also fetching labels.
- **List issues**: `gh issue list --repo visualhumanity/stash-plugins --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'` with appropriate `--label` and `--state` filters.
- **Comment on an issue**: `gh issue comment <number> --repo visualhumanity/stash-plugins --body "..."`
- **Apply / remove labels**: `gh issue edit <number> --repo visualhumanity/stash-plugins --add-label "..."` / `--remove-label "..."`
- **Close**: `gh issue close <number> --repo visualhumanity/stash-plugins --comment "..."`

## Pull requests as a triage surface

**PRs as a request surface: no.** _(Set to `yes` if this repo treats external PRs as feature requests; `/triage` reads this flag.)_

When set to `yes`, PRs run through the same labels and states as issues, using the `gh pr` equivalents (same token and `--repo` rule):

- **Read a PR**: `gh pr view <number> --comments` and `gh pr diff <number>` for the diff.
- **List external PRs for triage**: `gh pr list --state open --json number,title,body,labels,author,authorAssociation,comments` then keep only `authorAssociation` of `CONTRIBUTOR`, `FIRST_TIME_CONTRIBUTOR`, or `NONE` (drop `OWNER`/`MEMBER`/`COLLABORATOR`).
- **Comment / label / close**: `gh pr comment`, `gh pr edit --add-label`/`--remove-label`, `gh pr close`.

GitHub shares one number space across issues and PRs, so a bare `#42` may be either: resolve with `gh pr view 42` and fall back to `gh issue view 42`.

## When a skill says "publish to the issue tracker"

Create a GitHub issue.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --repo visualhumanity/stash-plugins --comments`.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a single issue with **child** issues as tickets. Same token and `--repo` rule as above.

- **Map**: a single issue labelled `wayfinder:map`, holding the Notes / Decisions-so-far / Fog body. `gh issue create --repo visualhumanity/stash-plugins --label wayfinder:map`.
- **Child ticket**: an issue linked to the map as a GitHub sub-issue (`gh api` on the sub-issues endpoint). Where sub-issues aren't enabled, add the child to a task list in the map body and put `Part of #<map>` at the top of the child body. Labels: `wayfinder:<type>` (`research`/`prototype`/`grilling`/`task`). Once claimed, the ticket is assigned to the driving dev.
- **Blocking**: GitHub's **native issue dependencies**, the UI-visible representation. Add an edge with `gh api --method POST repos/visualhumanity/stash-plugins/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`, where `<blocker-db-id>` is the blocker's numeric **database id** (`gh api repos/visualhumanity/stash-plugins/issues/<n> --jq .id`, _not_ the `#number` or `node_id`). GitHub reports `issue_dependencies_summary.blocked_by` (open blockers only, the live gate). Where dependencies aren't available, fall back to a `Blocked by: #<n>, #<n>` line at the top of the child body. A ticket is unblocked when every blocker is closed.
- **Frontier query**: list the map's open children (`gh issue list --repo visualhumanity/stash-plugins --state open`, limited to the map's sub-issues / task list), drop any with an open blocker (`issue_dependencies_summary.blocked_by > 0`, or an open issue in the `Blocked by` line) or an assignee; first in map order wins.
- **Claim**: `gh issue edit <n> --repo visualhumanity/stash-plugins --add-assignee @me`, the session's first write.
- **Resolve**: `gh issue comment <n> --body "<answer>"`, then `gh issue close <n>`, then append a context pointer (gist + link) to the map's Decisions-so-far.
