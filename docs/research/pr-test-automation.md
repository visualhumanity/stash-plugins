# Research: PR test automation for stash-plugins

**Question:** What is the best method to run the test suite for all plugins on PRs, to catch regressions before merging?

---

## Findings

### Test framework in use

Tests use Python's stdlib `unittest` module ([docs.python.org/3/library/unittest.html](https://docs.python.org/3/library/unittest.html)).

- Test files follow the `test_*.py` naming convention and live under `tests/<plugin_name>/`.
- No third-party test runner (pytest, tox, nose) is used or required.
- Discovery command: `python3 -m unittest discover -s tests/ -p "test_*.py" -v`
  — this scans `tests/` recursively and auto-discovers new test directories as plugins gain coverage.

One optional dependency: `PyYAML` is imported inside `ManifestTests` in `tests/vhClearFields/test_client_and_contracts.py`. The test self-skips when PyYAML is absent, but installing it gives full coverage. No other third-party packages are needed by the tests.

**Source:** direct inspection of `tests/vhClearFields/test_vhClearFields.py` and `tests/vhClearFields/test_client_and_contracts.py` in this repo.

### Current CI state

The existing `.github/workflows/deploy.yml` only triggers on pushes to `main` with path filters (`plugins/**`, `themes/**`, `build_site.sh`). It has no `pull_request` trigger and no test step. Tests are never run by CI today.

**Source:** `.github/workflows/deploy.yml` in this repo.

### Reference: sibling repo pattern

`stash-scrapers` (the sister repository) uses an almost-identical `deploy.yml` but adds a `pull_request:` trigger with no branch or path filter. Its `build` job therefore runs as a PR check. It has no test job either, but it demonstrates that a `pull_request:` trigger is the correct GitHub Actions primitive for gating merges.

**Source:** `.github/workflows/deploy.yml` in the `stash-scrapers` repository.

### Chosen approach

A separate `test.yml` workflow was added (`.github/workflows/test.yml`) with:

- **Trigger:** `pull_request` targeting `main` + `push` to `main`.
  — Keeps `deploy.yml` unchanged (single responsibility: build + deploy stays on main only).
- **Job `test`:** `ubuntu-latest`, install `pyyaml`, run `python3 -m unittest discover`.
  — No `fetch-depth` override needed (tests do not read git history).

**Why a separate workflow, not a new job in `deploy.yml`?** The deploy workflow only fires when `plugins/**` etc. change; a PR that only changes `tests/` or `.github/workflows/` would never trigger it. Keeping test and deploy separate also avoids re-deploying on test-only changes.

### Scaling

- `unittest discover` auto-finds `tests/<plugin>/test_*.py` — no workflow changes needed when new plugins gain tests.
- For many plugins or slow suites: add a matrix job keyed on test directories. GitHub Actions [matrix strategy](https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/running-variations-of-jobs-in-a-workflow) runs each entry in parallel.
- JS-only plugins need a separate `test-js` job (npm + jest/vitest) if they ever gain tests; the Python job cannot cover them.
- For dependency growth: add `tests/requirements.txt` and replace `pip install pyyaml` with `pip install -r tests/requirements.txt`.

### Making the test job a required check

After the workflow file merges, go to **Repository Settings > Branches > Branch protection rules** for `main` and add `test` as a required status check. This blocks merging a PR while the job is failing.

**Source:** [GitHub Docs — About protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
