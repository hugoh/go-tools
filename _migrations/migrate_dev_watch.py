"""Migrate the removed dev_watch answer to has_executable.

Run by copier's _migrations (before stage) during `copier update`, so the
new has_executable question resolves correctly for projects that relied on
dev_watch to skip `go run .` for a library with no main package. Idempotent:
once dev_watch is gone from .copier-answers.yml, this is a no-op.
"""

import os
import sys

ANSWERS_FILE = ".copier-answers.yml"


def migrate(path):
    if not os.path.exists(path):
        return

    with open(path) as f:
        lines = f.readlines()

    had_dev_watch_true = any(line.strip() == "dev_watch: true" for line in lines)
    has_executable_present = any(
        line.strip().startswith("has_executable:") for line in lines
    )
    lines = [line for line in lines if not line.strip().startswith("dev_watch:")]

    if had_dev_watch_true and not has_executable_present:
        lines.append("has_executable: false\n")

    with open(path, "w") as f:
        f.writelines(lines)


if __name__ == "__main__":
    migrate(ANSWERS_FILE)
    sys.exit(0)
