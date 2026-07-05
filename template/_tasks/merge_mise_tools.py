"""Merge missing tools from .mise-desired.toml into mise.toml.

Called by copier _tasks after template update. Adds any tool from the
freshly-rendered .mise-desired.toml that is absent from the Renovate-managed
mise.toml (which _skip_if_exists preserves). Cleans up .mise-desired.toml
after merging.
"""

import os
import re
import sys


KEY_RE = re.compile(
    r'^\s*(?:"(?P<quoted>[^"]+)"|(?P<bare>[^\s=]+))\s*=\s*"(?P<val>[^"]*)"\s*$',
)


def parse_tools(path):
    """Return dict of tool_name -> version from [tools] section."""
    tools = {}
    in_tools = False
    with open(path) as f:
        for line in f:
            s = line.strip()
            if s.startswith("[") and s.endswith("]"):
                in_tools = s.lower() == "[tools]"
                continue
            if not in_tools or not s or s.startswith("#"):
                continue
            m = KEY_RE.match(s)
            if m:
                tools[m.group("quoted") or m.group("bare")] = m.group("val")
    return tools


def main():
    dest = os.getcwd()
    desired_file = os.path.join(dest, ".mise-desired.toml")
    target_file = os.path.join(dest, "mise.toml")

    if not os.path.exists(desired_file):
        return

    desired = parse_tools(desired_file)
    if not desired:
        os.remove(desired_file)
        return

    existing = parse_tools(target_file) if os.path.exists(target_file) else {}

    missing = {k: v for k, v in desired.items() if k not in existing}
    if not missing:
        os.remove(desired_file)
        return

    with open(target_file) as f:
        content = f.read()

    lines = content.splitlines(keepends=True)

    tools_start = None
    tools_end = None
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            if tools_start is not None:
                tools_end = i
                break
            if s.lower() == "[tools]":
                tools_start = i

    if tools_start is None:
        insert_pos = len(lines)
        for i, line in enumerate(lines):
            if line.strip().startswith("["):
                insert_pos = i
                break
        insert = "[tools]\n"
    else:
        insert_pos = tools_end if tools_end is not None else len(lines)
        if insert_pos != len(lines):
            for i in range(insert_pos - 1, tools_start, -1):
                if lines[i].strip():
                    insert_pos = i + 1
                    break
        insert = ""

    for key in sorted(missing):
        k = f'"{key}"' if ("/" in key or ":" in key or "." in key) else key
        insert += f'{k} = "{missing[key]}"\n'

    lines.insert(insert_pos, insert)

    with open(target_file, "w") as f:
        f.writelines(lines)

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
