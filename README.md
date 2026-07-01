# go-tools

Shared tooling for [hugoh](https://github.com/hugoh)'s Go project repositories (`hrd`, `upd`, `tmhi-cli`, `tmhi-gateway`, `cellular-signal`, ...). Contains a Copier template for config files that don't support remote extends, reusable GitHub Actions workflows, and a Renovate config preset — things that would otherwise be copied into every repo.

---

## Copier template

Templates the config files every Go repo carries: `.golangci.yml`, `.testcoverage.yml`, `cog.toml`, `codecov.yml`, `dprint.json`, `hk.pkl`, `.jscpd.json`, `.markdownlint.json`, `.renovaterc.json`, `.github/workflows/{ci,template-update}.yml`, and the `mise-tasks/` directory (mise [file tasks](https://mise.jdx.dev/tasks/#file-tasks): lint, test, build, ci, etc).

`mise.toml` is templated too, but only to **seed** a new repo (`_skip_if_exists` in `copier.yml`) — once it exists, `copier update` never touches it again, so Renovate can freely bump tool versions there without ever fighting the template. mise automatically merges the `mise-tasks/` scripts in as tasks regardless of what's in `mise.toml`.

### Bootstrapping a brand-new repo

1. `go mod init`, write the code, `git init` — the parts this template doesn't (and shouldn't) own.
2. Run Copier via `uvx` (**not** `mise use pipx:copier`, which would create `mise.toml` itself before Copier gets a chance to seed it, tripping `_skip_if_exists` and leaving you with an empty tool list):

   ```sh
   uvx copier copy gh:hugoh/go-tools .
   ```

   Answer the prompts (`has_test_int`, `has_gen`, `coverage_total`, the `golangci_*` lists, etc). This generates every file above, including a starter `mise.toml` (which already pins `copier`, so it's mise-managed from here on), plus `.copier-answers.yml` to track the template going forward.
3. Push to GitHub, add the `CODECOV_TOKEN` secret if using Codecov, confirm Renovate is enabled (it'll pick up `.renovaterc.json` automatically).
4. `mise install && hk install && mise run ci` locally to confirm everything's green before the first push.

### Keeping a repo up to date

Each repo's `.github/workflows/template-update.yml` (itself part of the template) calls `go-template-update.yml`, which runs `copier update` and opens a PR when the template has changed. It's triggered three ways:

- **`repository_dispatch`** — `go-tools`'s own CI fires a `go-tools-updated` event to every repo listed in `consumers.txt` after a push to `main`. Needs a `DISPATCH_TOKEN` secret (repo-scoped PAT) on `go-tools`.
- **Weekly cron** — safety net in case a dispatch is missed.
- **`workflow_dispatch`** — manual trigger.

To do it by hand instead: `copier update` inside the repo (re-applies the template and 3-way-merges against local edits, recorded in `.copier-answers.yml`).

See `copier.yml` in this repo for the full list of variables (coverage thresholds, tool version pins, per-project golangci-lint deltas, etc).

---

## Reusable workflows

Referenced automatically by the templated `.github/workflows/ci.yml` via `uses:`. Not meant to be used directly, but documented here for completeness:

- `go-hk.yml` — runs `hk check` (lint/format/security checks via mise+hk).
- `go-ci.yml` — runs `mise ci` (build, test, coverage) and uploads coverage to Codecov.
- `go-release.yml` — cocogitto version bump + goreleaser release, triggered by a tag push (or dry-run validated on PRs).

---

## Renovate preset

Add to a repo's `.renovaterc.json` to inherit all shared Renovate config (this is what the Copier template generates):

```json
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": ["github>hugoh/go-tools"]
}
```

> **Note:** `default.json` in this repo root is the Renovate preset file. It is not package config.
