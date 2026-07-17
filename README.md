# go-tools

Shared tooling for [hugoh](https://github.com/hugoh)'s Go project repositories (`hrd`, `upd`, `tmhi-cli`, `tmhi-gateway`, `cellular-signal`, ...). Contains a Copier template for config files that don't support remote extends, reusable GitHub Actions workflows, and a Renovate config preset — things that would otherwise be copied into every repo.

---

## Copier template

Templates the config files every Go repo carries: `.golangci.yml`, `.testcoverage.yml`, `cog.toml`, `dprint.json`, `hk.pkl`, `.jscpd.json`, `.markdownlint.json`, `.renovaterc.json`, `.github/workflows/ci.yml`, and the `mise-tasks/` directory (mise [file tasks](https://mise.jdx.dev/tasks/#file-tasks): lint, test, build, ci, etc).

`mise.toml` is templated too, and — like `hk.pkl` — is re-rendered on every `copier update`; it's not `_skip_if_exists`'d. `go-renovaterc.json` disables Renovate's `mise` manager for `mise.toml` in consumer repos so the two don't race to bump the same tool versions (see `hk.pkl`'s note below for the same pattern). mise automatically merges the `mise-tasks/` scripts in as tasks regardless of what's in `mise.toml`.

### Bootstrapping a brand-new repo

1. `go mod init`, write the code, `git init` — the parts this template doesn't (and shouldn't) own.
2. Run Copier via `uvx`:

   ```sh
   uvx copier copy https://github.com/hugoh/go-tools.git .
   ```

   Answer the prompts (`has_test_int`, `has_gen`, `coverage_total`, the `golangci_*` lists, etc). This generates every file above, including a starter `mise.toml` (which already pins `copier`, so it's mise-managed from here on), plus `.copier-answers.yml` to track the template going forward.
3. Push to GitHub, add the `CODECOV_TOKEN` secret if using Codecov (and `TAP_GITHUB_TOKEN` if `has_homebrew_cask` is set — needed by `go-release.yml` to publish the Homebrew cask), confirm Renovate is enabled (it'll pick up `.renovaterc.json` automatically). Renovate will also detect `.copier-answers.yml` and create template update PRs automatically going forward.
4. `mise install && hk install && mise run ci` locally to confirm everything's green before the first push.
5. `mise run gh-repo-setup owner/repo` — one-time branch protection (PR required, `hk`/`goci`/`release` required checks, no direct pushes), auto-merge, and delete-branch-on-merge. Requires `gh auth login` with a token that has repo admin access.

### Keeping a repo up to date

Template updates are handled by **Renovate's built-in copier manager**. When a new version of `go-tools` is tagged, Renovate detects the outdated `_commit` in `.copier-answers.yml`, runs `copier update`, and opens a PR. Schedule: at any time.

`copier.yml` pins `_src_path` to the full `https://github.com/hugoh/go-tools.git` URL, which gets force-written into every consumer's `.copier-answers.yml` regardless of how `copier copy`/`copier update` was actually invoked. This works around a Renovate limitation: its copier manager passes `_src_path` straight to git as a remote, so Copier's `gh:owner/repo` shorthand (which Copier itself expands internally, but records unexpanded in `.copier-answers.yml`) isn't resolvable and silently breaks update detection ([renovatebot/renovate#39938](https://github.com/renovatebot/renovate/issues/39938) tracks adding `gh:`/`gl:` support upstream). Because of this pin, bootstrapping with `gh:hugoh/go-tools` (as shown above) is safe — the recorded source is corrected regardless.

The three self-referential `hugoh/go-tools/...@<sha>` pins (`go-hk.yml`, `go-ci.yml`, `go-release.yml`) are managed exclusively by `copier update` — `go-renovaterc.json` disables Renovate's `github-actions` manager for `hugoh/go-tools` to prevent merge conflicts. Renovate manages every other action pin fleet-wide as usual.

The `hk-config` Pkl package pin in `hk.pkl` follows the same rule: consumer repos' `hk.pkl` is a Copier output, re-rendered on every `copier update`, so it must only change via that same template-update PR — never via a direct in-place edit that would then conflict with the next `copier update`'s merge. That's why `go-renovaterc.json` (the **shared** preset consumer repos extend) deliberately does **not** extend `hugoh/hk-config`'s own Renovate config, unlike every other hugoh repo. The pin only moves once `template/hk.pkl.jinja`'s own copy of it is bumped and a new `go-tools` release/commit lands, at which point the existing "always automerge template updates" `packageRule` above picks it up like any other template change.

`go-tools`' own `.renovaterc.json` (this repo's config, distinct from the `go-renovaterc.json` preset it publishes) is the one exception that _does_ extend `hugoh/hk-config`'s Renovate config directly, plus two extra `customManagers` scoped to `template/hk.pkl.jinja` — because both `go-tools/hk.pkl` (hand-maintained repo tooling, not a Copier output) and the `.jinja` template source itself (nothing else keeps its embedded pin current) are this repo's own to manage, not something `copier update` touches.

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

### Manually forcing a version bump in a consumer repo

`cog bump --auto` (the default, run on every push to `main`) never crosses the `0.x → 1.x` boundary on its own — per SemVer, a breaking change in `0.x.y` bumps the _minor_, since anything can break pre-1.0 by definition. To force a specific bump through the normal, checked pipeline (`hk` → `goci` → `release`) instead of bypassing CI entirely, a repo built from this template (with `has_goreleaser: true`) can trigger its `ci.yml` manually with a `bump_type`:

```sh
gh workflow run ci.yml --ref main -f bump_type=major
```

(`bump_type` accepts `auto` (default), `patch`, `minor`, or `major`; also available via the Actions tab's "Run workflow" button.) The dispatch must target `main` — `go-release.yml` fails fast otherwise — and still runs `hk`/`goci` before releasing.

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
