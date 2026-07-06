"""Render the Copier template against fixtures and validate the output.

Invoked via `mise run render-check` (a thin shim delegating to
`uv run --with pytest --with pytest-xdist pytest -n auto`), and as part of
hk's `render-check` step and CI's `hk` job.
"""

import fcntl
import glob
import os
import subprocess
from contextlib import contextmanager
from pathlib import Path

import pytest

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

    def check(name, check_cmd, cwd=tmp_path, env=None):
        ok, log = run(check_cmd, cwd=cwd, env=env)
        if not ok:
            failures.append(f"{name} failed:\n{log}")

    check(
        "shellcheck",
        ["shellcheck", *glob.glob(str(tmp_path / "mise-tasks" / "*"))],
    )
    check(
        "actionlint",
        ["actionlint", *glob.glob(str(tmp_path / ".github" / "workflows" / "*.yml"))],
    )
    check("dprint check", ["dprint", "check"])

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
