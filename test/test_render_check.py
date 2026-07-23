"""Render the Copier template against fixtures and validate the output.

Invoked via `mise run render-check` (a thin shim delegating to
`uv run --with pytest --with pytest-xdist pytest -n auto`), and as part of
hk's `render-check` step and CI's `hk` job.
"""

import fcntl
import glob
import hashlib
import json
import os
import subprocess
import tomllib
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

import copier
import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent

FIXTURES = sorted((ROOT / "test" / "fixtures").glob("*.yml"))
CASES = [(f.stem, f) for f in FIXTURES] + [("defaults", None)]

# copier.run_copy(vcs_ref="HEAD") warns whenever ROOT's git working tree has
# uncommitted changes, which is routinely true while iterating locally (and
# harmless: it's just describing how it already resolves "HEAD" against a
# dirty tree, not a problem with the render).
pytestmark = pytest.mark.filterwarnings("ignore::copier.errors.DirtyLocalWarning")


@contextmanager
def file_lock(path):
    """Serialize a block across pytest-xdist worker processes.

    hk's `validate` reads/writes a shared pkl package cache (~/.pkl/cache)
    that isn't safe under concurrent access (observed: intermittent,
    differing pkl parse errors across parallel tmpdirs, even with each
    tmpdir given its own HK_CACHE_DIR).
    """
    with open(path, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def run(cmd, cwd=None, env=None):
    proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    return proc.returncode == 0, proc.stdout + proc.stderr


@pytest.mark.parametrize("label,data_file", CASES, ids=[c[0] for c in CASES])
def test_render_and_validate(label, data_file, tmp_path, tmp_path_factory):
    # Calling copier's own Python API in-process instead of shelling out to
    # the `copier` CLI avoids paying a fresh Python-interpreter startup cost
    # per case (6x here, more with more fixtures).
    answers = yaml.safe_load(data_file.read_text()) if data_file is not None else {}
    try:
        copier.run_copy(
            str(ROOT),
            str(tmp_path),
            data={**answers, "project_name": label},
            vcs_ref="HEAD",
            defaults=True,
            unsafe=True,
            quiet=True,
        )
    except Exception as e:  # noqa: BLE001 - report any render failure as a test failure
        pytest.fail(f"copier render failed:\n{e}", pytrace=False)

    failures = []

    expect_dev = answers.get("has_executable", True)
    dev_exists = (tmp_path / "mise-tasks" / "dev").exists()
    if dev_exists != expect_dev:
        failures.append(
            f"mise-tasks/dev existence ({dev_exists}) doesn't match "
            f"has_executable ({expect_dev})",
        )

    try:
        tomllib.loads((tmp_path / "mise.toml").read_text())
    except tomllib.TOMLDecodeError as e:
        failures.append(f"generated mise.toml is not valid TOML:\n{e}")

    cache_dir = tmp_path_factory.getbasetemp().parent
    hk_lock_path = cache_dir / "hk-validate.lock"

    def cached_check(check_name, inputs, fn):
        """Run fn() once per unique content of `inputs`, sharing the result
        with any other case (in any xdist worker) whose inputs hash the same.

        Only worth it for checks scoped to specific files/globs, where
        several cases plausibly render byte-identical content (e.g. most
        mise-tasks/* scripts and mise.toml's [tools] table aren't
        project_name-parameterized). Checks that scan the whole rendered
        tree ('.') aren't wrapped in this - they almost always differ by
        project_name/description alone, so hashing the full tree would just
        add cost without ever hitting the cache.
        """
        hasher = hashlib.sha256()
        for p in sorted(Path(p) for p in inputs):
            hasher.update(str(p.relative_to(tmp_path)).encode())
            hasher.update(p.read_bytes())
        key = f"{check_name}-{hasher.hexdigest()[:16]}"
        result_path = cache_dir / f"{key}.json"
        lock_path = cache_dir / f"{key}.lock"
        with file_lock(lock_path):
            if result_path.exists():
                cached = json.loads(result_path.read_text())
                return cached["ok"], cached["log"]
            ok, log = fn()
            result_path.write_text(json.dumps({"ok": ok, "log": log}))
            return ok, log

    mise_tasks_files = glob.glob(str(tmp_path / "mise-tasks" / "*"))
    workflow_files = glob.glob(str(tmp_path / ".github" / "workflows" / "*.yml"))

    def hk_validate():
        def run_locked():
            # hk's `validate` reads/writes a shared pkl package cache
            # (~/.pkl/cache) that isn't safe under concurrent access
            # (observed: intermittent, differing pkl parse errors across
            # parallel tmpdirs, even with each tmpdir given its own
            # HK_CACHE_DIR) - serialize against other xdist worker
            # processes via file_lock. It can still run concurrently with
            # this case's other, unrelated checks.
            with file_lock(hk_lock_path):
                return run(["hk", "validate"], cwd=tmp_path)

        return cached_check("hk-validate", [tmp_path / "hk.pkl"], run_locked)

    def mise_install():
        def do_install():
            return run(
                ["mise", "install"],
                cwd=tmp_path,
                env={
                    **os.environ,
                    "MISE_TRUSTED_CONFIG_PATHS": str(tmp_path),
                    "MISE_YES": "1",
                    # Fresh CI runners (no user mise config) default the npm
                    # backend to aube, which enforces stricter checks than
                    # npm/bun - notably rejecting packages that drop
                    # provenance attestation after a prior version had it.
                    # Force it here so render-check matches what consumer
                    # repos' CI actually hits, rather than whatever backend
                    # happens to be configured on the machine running this
                    # test.
                    "MISE_NPM_PACKAGE_MANAGER": "aube",
                },
            )

        # Only has_goreleaser varies the rendered [tools] table across
        # cases - every other tool pin is unconditional - so most cases
        # share byte-identical mise.toml content.
        return cached_check("mise-install", [tmp_path / "mise.toml"], do_install)

    checks = {
        "shellcheck": lambda: cached_check(
            "shellcheck",
            mise_tasks_files,
            lambda: run(["shellcheck", *mise_tasks_files]),
        ),
        "shellharden": lambda: cached_check(
            "shellharden",
            mise_tasks_files,
            lambda: run(["shellharden", "--check", *mise_tasks_files]),
        ),
        "actionlint": lambda: cached_check(
            "actionlint",
            workflow_files,
            lambda: run(["actionlint", *workflow_files]),
        ),
        "rumdl check": lambda: run(
            ["rumdl", "check", "--exclude", "README.md", "."],
            cwd=tmp_path,
        ),
        "tombi format check": lambda: run(
            ["tombi", "format", "--check", "."],
            cwd=tmp_path,
        ),
        # ryl is deliberately not checked here: it requires a rules config
        # (.yamllint/ryl.toml) to do anything, and that file is
        # hand-maintained per consumer repo, not part of this Copier
        # template's own output.
        "biome check": lambda: run(
            ["biome", "check", "--no-errors-on-unmatched", "."],
            cwd=tmp_path,
        ),
        "mise install": mise_install,
        "hk validate": hk_validate,
    }

    if (tmp_path / ".goreleaser.yml").exists():
        run(["git", "init", "-q"], cwd=tmp_path)
        run(
            ["git", "remote", "add", "origin", f"https://github.com/hugoh/{label}.git"],
            cwd=tmp_path,
        )
        checks["goreleaser check"] = lambda: run(
            ["goreleaser", "check"],
            cwd=tmp_path,
            env={**os.environ, "TAP_GITHUB_TOKEN": "x"},
        )

    # These checks are independent of each other (aside from hk_validate's
    # own cross-process locking above), so run them concurrently rather than
    # one at a time - subprocess.run releases the GIL while blocked, so
    # threads are enough here without an asyncio rewrite. Sized as this
    # worker's fair share of the machine's CPUs: pytest-xdist is running
    # PYTEST_XDIST_WORKER_COUNT copies of this same pool concurrently for
    # other cases, so dividing avoids the combined thread count oversubscribing
    # the machine. Never exceeds len(checks), since more threads than tasks
    # buys nothing.
    xdist_workers = int(os.environ.get("PYTEST_XDIST_WORKER_COUNT", 1))
    max_workers = max(1, min(len(checks), (os.cpu_count() or 4) // xdist_workers))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        results = dict(zip(checks, pool.map(lambda fn: fn(), checks.values())))

    for name, (ok, log) in results.items():
        if not ok:
            failures.append(f"{name} failed:\n{log}")

    if failures:
        pytest.fail("\n\n".join(failures), pytrace=False)


def test_mise_toml_jinja_is_raw_toml():
    """template/mise.toml.jinja must parse as TOML in its raw, unrendered form.

    Renovate's `mise` manager reads this file as literal TOML *before* any
    Jinja rendering happens, to keep tool pins (hk, etc.) current. A Jinja
    block tag written on its own line (e.g. an `[%- if %]`) is indistinguishable
    from a TOML table header to that parser, which silently drops every pin in
    the file from Renovate's view — not just the one inside the conditional.
    This regression is invisible to the render-check above, since it only
    ever inspects the *rendered* output, never the raw template source.
    """
    raw = (ROOT / "template" / "mise.toml.jinja").read_text()
    try:
        tomllib.loads(raw)
    except tomllib.TOMLDecodeError as e:
        pytest.fail(
            "template/mise.toml.jinja isn't valid TOML in its raw, "
            "unrendered form, which means Renovate's `mise` manager can't "
            "parse it and silently stops tracking every tool pin in this "
            "file. Any Jinja control-flow tag (`[%- if %]`, `[%- endif %]`, "
            "etc.) must be kept behind a leading `#` so the raw source still "
            "reads as a TOML comment line to a plain TOML parser.\n\n"
            f"{e}",
            pytrace=False,
        )
