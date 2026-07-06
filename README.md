# go-tools

Shared tooling for [hugoh](https://github.com/hugoh)'s Go project repositories (`hrd`, `upd`, `tmhi-cli`, `tmhi-gateway`, `cellular-signal`, ...). Contains a Copier template for config files that don't support remote extends, reusable GitHub Actions workflows, and a Renovate config preset — things that would otherwise be copied into every repo.

---

## Copier template

Templates the config files every Go repo carries: `.golangci.yml`, `.testcoverage.yml`, `cog.toml`, `codecov.yml`, `dprint.json`, `hk.pkl`, `.jscpd.json`, `.markdownlint.json`, `.renovaterc.json`, `.github/workflows/ci.yml`, and the `mise-tasks/` directory (mise [file tasks](https://mise.jdx.dev/tasks/#file-tasks): lint, test, build, ci, etc).

`mise.toml` is templated too, but only to **seed** a new repo (`_skip_if_exists` in `copier.yml`) — once it exists, `copier update` never touches it again, so Renovate can freely bump tool versions there without ever fighting the template. mise automatically merges the `mise-tasks/` scripts in as tasks regardless of what's in `mise.toml`.

### Bootstrapping a brand-new repo

1. `go mod init`, write the code, `git init` — the parts this template doesn't (and shouldn't) own.
2. Run Copier via `uvx` (**not** `mise use pipx:copier`, which would create `mise.toml` itself before Copier gets a chance to seed it, tripping `_skip_if_exists` and leaving you with an empty tool list):

   ```sh
   uvx copier copy --trust https://github.com/hugoh/go-tools .
   ```

   Answer the prompts (`has_test_int`, `has_gen`, `coverage_total`, the `golangci_*` lists, etc). This generates every file above, including a starter `mise.toml` (which already pins `copier`, so it's mise-managed from here on), plus `.copier-answers.yml` to track the template going forward.
3. Push to GitHub, add the `CODECOV_TOKEN` secret if using Codecov (and `TAP_GITHUB_TOKEN` if `has_homebrew_cask` is set — needed by `go-release.yml` to publish the Homebrew cask), confirm Renovate is enabled (it'll pick up `.renovaterc.json` automatically). Renovate will also detect `.copier-answers.yml` and create template update PRs automatically going forward.
4. `mise install && hk install && mise run ci` locally to confirm everything's green before the first push.
5. `mise run gh-repo-setup owner/repo` — one-time branch protection (PR required, `hk`/`goci`/`release` required checks, no direct pushes), auto-merge, and delete-branch-on-merge. Requires `gh auth login` with a token that has repo admin access.

### Keeping a repo up to date

Template updates are handled by **Renovate's built-in copier manager**. When a new version of `go-tools` is tagged, Renovate detects the outdated `_commit` in `.copier-answers.yml`, runs `copier update`, and opens a PR. Schedule: at any time.

`copier.yml` pins `_src_path` to the full `https://github.com/hugoh/go-tools.git` URL, which gets force-written into every consumer's `.copier-answers.yml` regardless of how `copier copy`/`copier update` was actually invoked. This works around a Renovate limitation: its copier manager passes `_src_path` straight to git as a remote, so Copier's `gh:owner/repo` shorthand (which Copier itself expands internally, but records unexpanded in `.copier-answers.yml`) isn't resolvable and silently breaks update detection ([renovatebot/renovate#39938](https://github.com/renovatebot/renovate/issues/39938) tracks adding `gh:`/`gl:` support upstream). Because of this pin, bootstrapping with `gh:hugoh/go-tools` (as shown above) is safe — the recorded source is corrected regardless.

Consumer repos' `mise.toml` is never overwritten by `copier update` (see `_skip_if_exists` above), but new tools added to the template's tool list _are_ still propagated: a post-update task (`_tasks/merge_mise_tools.py`, self-destructing after it runs) merges any tool missing from the existing `mise.toml` in from a generated `.mise-desired.toml`, then deletes that scratch file. Existing tool pins (including ones Renovate has since bumped) are left untouched — only missing keys are added.

The three self-referential `hugoh/go-tools/...@<sha>` pins (`go-hk.yml`, `go-ci.yml`, `go-release.yml`) are managed exclusively by `copier update` — `go-renovaterc.json` disables Renovate's `github-actions` manager for `hugoh/go-tools` to prevent merge conflicts. Renovate manages every other action pin fleet-wide as usual.

To update by hand: run `copier update` inside the repo.

See `copier.yml` in this repo for the full list of variables (coverage thresholds, tool version pins, per-project golangci-lint deltas, etc).

### Releasing go-tools itself

`go-tools`'s own `ci.yml` has a `release` job (push-to-main only, after `hk` passes) that runs `cocogitto bump --auto` and pushes the resulting tag using the default `GITHUB_TOKEN`. Version bumps follow Conventional Commits as usual (`fix:` → patch, `feat:` → minor, breaking change → major); merge a conventional-commit PR to main and a new tag appears automatically. No manual `git tag` is needed.

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
  "extends": ["github>hugoh/go-tools:go-renovaterc"]
}
```

> **Note:** `go-renovaterc.json` in this repo root is the Renovate preset file. It is not package config.
