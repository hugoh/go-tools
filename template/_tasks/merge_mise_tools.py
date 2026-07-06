# /// script
# requires-python = ">=3.11"
# dependencies = ["tomlkit>=0.12,<1"]
# ///
"""Merge missing tools from .mise-desired.toml into mise.toml.

Called by copier _tasks after template update. Adds any tool from the
freshly-rendered .mise-desired.toml that is absent from the Renovate-managed
mise.toml (which _skip_if_exists preserves). Cleans up .mise-desired.toml
after merging.
"""

import os
import sys

import tomlkit


def parse_tools(path):
    """Return dict of tool_name -> value from the [tools] section."""
    with open(path) as f:
        doc = tomlkit.parse(f.read())
    return dict(doc.get("tools", {}))


def merge_missing(existing_doc, missing):
    """Add missing tools into existing_doc's [tools] table, creating it at
    the top of the document if it doesn't exist yet.

    tomlkit has no public API to insert a new table at an explicit position,
    so this uses Container._insert_at (private) to match the convention that
    [tools] appears first in a freshly-created mise.toml.
    """
    if "tools" not in existing_doc:
        new_table = tomlkit.table()
        if len(existing_doc.body) == 0:
            existing_doc.add("tools", new_table)
        else:
            existing_doc._insert_at(0, "tools", new_table)  # noqa: SLF001
    tools_table = existing_doc["tools"]
    for key in sorted(missing):
        tools_table[key] = missing[key]


def main():
    dest = os.getcwd()
    desired_file = os.path.join(dest, ".mise-desired.toml")
    target_file = os.path.join(dest, "mise.toml")

    if not os.path.exists(desired_file):
        return

    with open(desired_file) as f:
        desired_doc = tomlkit.parse(f.read())
    desired = dict(desired_doc.get("tools", {}))

    if not desired:
        os.remove(desired_file)
        return

    if os.path.exists(target_file):
        with open(target_file) as f:
            existing_doc = tomlkit.parse(f.read())
    else:
        existing_doc = tomlkit.document()

    existing = dict(existing_doc.get("tools", {}))

    missing = {k: v for k, v in desired.items() if k not in existing}
    if not missing:
        os.remove(desired_file)
        return

    merge_missing(existing_doc, missing)

    with open(target_file, "w") as f:
        f.write(tomlkit.dumps(existing_doc))

    os.remove(desired_file)
    print(
        f"merge-mise-tools: added {len(missing)} tool(s) to mise.toml: "
        f"{', '.join(sorted(missing.keys()))}",
    )


if __name__ == "__main__":
    main()
    if "--self-destruct" in sys.argv:
        self_path = os.path.join(os.getcwd(), "_tasks", "merge_mise_tools.py")
        if os.path.exists(self_path):
            os.remove(self_path)
