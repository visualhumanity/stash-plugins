# Stash Plugins

Plugins for Stash, published from this repo to two source indexes: one for users and one for testing.

## Language

### Publishing

**Source index**:
The `index.yml` file that Stash reads to list the plugins it can install from a source, together with the zip files it points to.
_Avoid_: feed, repo index

**Production index**:
The source index built from `main`. It holds released plugins, which users install from.
_Avoid_: release index, stable index, main index

**Develop index**:
The source index built from `develop`. It holds pre-release builds, which are tested on a test Stash instance.
_Avoid_: pre-release index, dev index, staging index

**Release PR**:
A pull request from `develop` into `main`.
_Avoid_: deploy PR, merge-up

**Promotion**:
Moving changes from `develop` to `main` through a release PR.
_Avoid_: deploy, publish

### Versioning

**First release version**:
`1.0.0`, the version a plugin must have when it first reaches `main`; before that it stays `0.Y.Z` on `develop`.
_Avoid_: calling the bump to `1.0.0` a "promotion" (promotion is the branch move)
