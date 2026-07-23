"""Render the Copier template against fixtures and validate the output.

Invoked via `mise run render-check` (a thin shim delegating to
`uv run --with pytest --with pytest-xdist pytest -n auto`), and as part of
hk's `render-check` step and CI's `hk` job.
"""

import fcntl
import glob
import os
import subprocess
import tomllib
from contextlib import contextmanager
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent

FIXTURES = sorted((ROOT / "test" / "fixtures").glob("*.yml"))
CASES = [(f.stem, f) for f in FIXTURES] + [("defaults", None)]


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
    cmd = [
        "copier",
        "copy",
        "--trust",
        "--vcs-ref=HEAD",
        "--defaults",
        "-d",
        f"project_name={label}",
    ]
    if data_file is not None:
        cmd += ["--data-file", str(data_file)]
    cmd += [str(ROOT), str(tmp_path)]

    ok, log = run(cmd)
    assert ok, f"copier render failed:\n{log}"

    failures = []

    answers = yaml.safe_load(data_file.read_text()) if data_file is not None else {}
    expect_dev = answers.get("has_executable", True)
    dev_exists = (tmp_path / "mise-tasks" / "dev").exists()
    if dev_exists != expect_dev:
        failures.append(
            f"mise-tasks/dev existence ({dev_exists}) doesn't match "
            f"has_executable ({expect_dev})",
        )

    def check(name, check_cmd, cwd=tmp_path, env=None):
        ok, log = run(check_cmd, cwd=cwd, env=env)
        if not ok:
            failures.append(f"{name} failed:\n{log}")

    check(
        "shellcheck",
        ["shellcheck", *glob.glob(str(tmp_path / "mise-tasks" / "*"))],
    )
    check(
        "shellharden",
        ["shellharden", "--check", *glob.glob(str(tmp_path / "mise-tasks" / "*"))],
    )
    check(
        "actionlint",
        ["actionlint", *glob.glob(str(tmp_path / ".github" / "workflows" / "*.yml"))],
    )
    check("rumdl check", ["rumdl", "check", "--exclude", "README.md", "."])
    check("tombi format check", ["tombi", "format", "--check", "."])
    # ryl is deliberately not checked here: it requires a rules config
    # (.yamllint/ryl.toml) to do anything, and that file is hand-maintained
    # per consumer repo, not part of this Copier template's own output.
    check("biome check", ["biome", "check", "--no-errors-on-unmatched", "."])

    lock_path = tmp_path_factory.getbasetemp().parent / "hk-validate.lock"
    with file_lock(lock_path):
        check("hk validate", ["hk", "validate"])

    if (tmp_path / ".goreleaser.yml").exists():
        run(["git", "init", "-q"], cwd=tmp_path)
        run(
            ["git", "remote", "add", "origin", f"https://github.com/hugoh/{label}.git"],
            cwd=tmp_path,
        )
        check(
            "goreleaser check",
            ["goreleaser", "check"],
            env={**os.environ, "TAP_GITHUB_TOKEN": "x"},
        )

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
