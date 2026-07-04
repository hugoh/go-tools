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
5. `mise run gh-repo-setup owner/repo` — one-time branch protection (PR required, `hk`/`goci`/`release` required checks, no direct pushes), auto-merge, and delete-branch-on-merge.
6. Add the repo to `consumers.txt` in this repo (used by `mise run set-template-update-token` to provision secrets — see below), and make sure it has the `TEMPLATE_UPDATE_TOKEN` secret set (see [Required secrets](#required-secrets)) so it can receive template updates.

### Keeping a repo up to date

Each repo's `.github/workflows/template-update.yml` (itself part of the template) calls `go-template-update.yml`, which runs `copier update` and opens a PR when the template has changed. It's triggered two ways:

- **Weekly cron** — every Monday at 06:00.
- **`workflow_dispatch`** — manual trigger, e.g. to bootstrap a repo onto a new template-update workflow revision, or to force an immediate resync instead of waiting for cron.

The four self-referential `hugoh/go-tools/...@<sha>` pins (`go-hk.yml`, `go-ci.yml`, `go-release.yml`, `go-template-update.yml`) are pinned by `copier update` itself, not Renovate — the Renovate preset (`default.json`) explicitly disables the `hugoh/go-tools` package for the `github-actions` manager. Copier's 3-way merge assumes it's the sole writer of anything it templates; letting Renovate _also_ bump these same lines made every `copier update` conflict with whatever Renovate had done in between (found the hard way — a `copier update` run failing with literal `<<<<<<<` conflict markers on that exact line, repeatedly, no matter how the underlying discrepancy was patched). Renovate still manages every other action pin fleet-wide as usual; this exclusion is scoped to `hugoh/go-tools` only.

To do it by hand instead: `copier update` inside the repo (re-applies the template and 3-way-merges against local edits, recorded in `.copier-answers.yml`).

See `copier.yml` in this repo for the full list of variables (coverage thresholds, tool version pins, per-project golangci-lint deltas, etc).

### Releasing go-tools itself

`go-tools`'s own `ci.yml` has a `release` job (push-to-main only, after `hk` passes) that runs `cocogitto bump --auto` and pushes the resulting tag using the default `GITHUB_TOKEN` — no PAT needed, since pushing a tag isn't subject to the workflow-file write restriction that `TEMPLATE_UPDATE_TOKEN` exists for. Version bumps follow Conventional Commits as usual (`fix:` → patch, `feat:` → minor, breaking change → major); merge a conventional-commit PR to main and a new tag appears automatically. No manual `git tag` is needed.

### Required secrets

- **`TEMPLATE_UPDATE_TOKEN`** (on every consumer repo) — [fine-grained PAT](https://github.com/settings/personal-access-tokens) `go-template-update.yml` uses to push the update branch and open/auto-merge the PR. Its repository access must cover every repo in `consumers.txt`, and it needs all three of:
  - **Contents: Read and write** — to push the `go-tools-update/<sha>` branch.
  - **Pull requests: Read and write** — to open and auto-merge the PR. Missing this makes `git push` succeed but `gh pr create` fail with `Resource not accessible by personal access token`; `go-template-update.yml` treats that as fatal, so it shows up as a failed run rather than a silent no-op.
  - **Workflows: Read and write** — the pushed branch includes changes to `.github/workflows/ci.yml` and `.github/workflows/template-update.yml` (the pinned `vcs_ref_hash` bumps on every `copier update`); GitHub rejects PAT pushes touching `.github/workflows/*` without this.

  Set it with `mise run set-template-update-token` — prompts for the value with echo suppressed (don't pipe a secret in via `echo`, it'll land in shell history) and pushes it to every repo in `consumers.txt`.

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
