"""Tests for merge-mise-tools.py."""

import os

import pytest
import tomlkit
import tomlkit.exceptions

from merge_mise_tools import main, parse_tools

PARSE_TOOLS_CASES = [
    pytest.param(
        '[tools]\ngo = "1.26.4"\ngolangci-lint = "2.12.2"\n',
        {"go": "1.26.4", "golangci-lint": "2.12.2"},
        id="bare_keys",
    ),
    pytest.param(
        '[tools]\n"go:golang.org/x/vuln/cmd/govulncheck" = "1.1.4"\n',
        {"go:golang.org/x/vuln/cmd/govulncheck": "1.1.4"},
        id="quoted_keys",
    ),
    pytest.param(
        '[tools]\ngo = "1.26.4"\n\n[env]\nCOVEROUT = "cover.out"\n',
        {"go": "1.26.4"},
        id="ignores_other_sections",
    ),
    pytest.param(
        '[tools]\ngo = "1.26.4"\n\n[settings]\ntask.timings = false\n',
        {"go": "1.26.4"},
        id="ignores_settings_section",
    ),
    pytest.param("", {}, id="empty_file"),
    pytest.param('[env]\nCOVEROUT = "cover.out"\n', {}, id="no_tools_section"),
    pytest.param(
        '[tools]\n# this is a comment\ngo = "1.26.4"\n',
        {"go": "1.26.4"},
        id="comments_skipped",
    ),
    pytest.param(
        '[tools]\ngo = "1.26.4"\n\n\n[env]\n',
        {"go": "1.26.4"},
        id="blank_lines_skipped",
    ),
    pytest.param(
        "[tools]\n"
        '"npm:cpd" = "5.0.11"\n'
        '"go:golang.org/x/tools/cmd/deadcode" = "0.46.0"\n',
        {
            "npm:cpd": "5.0.11",
            "go:golang.org/x/tools/cmd/deadcode": "0.46.0",
        },
        id="quoted_value_contains_dots_slashes",
    ),
]


@pytest.mark.parametrize("content,expected", PARSE_TOOLS_CASES)
def test_parse_tools(tmp_path, content, expected):
    path = tmp_path / "test.toml"
    path.write_text(content)
    assert parse_tools(str(path)) == expected


def test_parse_tools_inline_table_value_recognized(tmp_path):
    path = tmp_path / "test.toml"
    path.write_text(
        '[tools]\ngo = { version = "1.26.4", postinstall = "echo hi" }\nruff = "0.11.4"\n',
    )
    tools = parse_tools(str(path))
    assert "go" in tools
    assert tools["ruff"] == "0.11.4"
    assert tools["go"]["version"] == "1.26.4"


def test_parse_tools_raises_on_invalid_toml(tmp_path):
    path = tmp_path / "test.toml"
    path.write_text('[tools]\ngo = "1.26.4\n')  # unterminated string
    with pytest.raises(tomlkit.exceptions.TOMLKitError):
        parse_tools(str(path))


def _run_merge(tmp_path, monkeypatch, desired, target):
    (tmp_path / ".mise-desired.toml").write_text(desired)
    (tmp_path / "mise.toml").write_text(target)
    monkeypatch.chdir(tmp_path)
    main()
    return (tmp_path / "mise.toml").read_text()


def test_merge_adds_new_tool_inside_tools_section(tmp_path, monkeypatch):
    result = _run_merge(
        tmp_path,
        monkeypatch,
        '[tools]\ngo = "1.26.4"\nruff = "0.11.4"\n',
        '[tools]\ngo = "1.26.4"\n\n[env]\nCOVEROUT = "cover.out"\n',
    )
    assert 'ruff = "0.11.4"' in result
    assert ".mise-desired.toml" not in os.listdir(tmp_path)


def test_merge_skips_existing_tools(tmp_path, monkeypatch):
    result = _run_merge(
        tmp_path,
        monkeypatch,
        '[tools]\ngo = "1.26.4"\nruff = "0.11.4"\n',
        '[tools]\ngo = "1.26.4"\nruff = "0.9.0"\n\n[env]\nCOVEROUT = "cover.out"\n',
    )
    # Existing pin preserved — no duplicate
    assert 'ruff = "0.9.0"' in result
    assert result.count("ruff") == 1


def test_merge_no_op_when_nothing_missing(tmp_path, monkeypatch):
    target = '[tools]\ngo = "1.26.4"\nruff = "0.9.0"\n'
    result = _run_merge(tmp_path, monkeypatch, '[tools]\ngo = "1.26.4"\n', target)
    # mise.toml left byte-for-byte untouched when there's nothing to add
    assert result == target
    assert ".mise-desired.toml" not in os.listdir(tmp_path)


def test_merge_adds_tools_section_when_missing(tmp_path, monkeypatch):
    result = _run_merge(
        tmp_path,
        monkeypatch,
        '[tools]\nruff = "0.11.4"\n',
        '[env]\nCOVEROUT = "cover.out"\n',
    )
    assert "[tools]" in result
    assert 'ruff = "0.11.4"' in result
    # newly-created [tools] table is placed first, matching existing convention
    assert result.index("[tools]") < result.index("[env]")


def test_merge_creates_mise_toml_when_absent(tmp_path, monkeypatch):
    (tmp_path / ".mise-desired.toml").write_text('[tools]\nruff = "0.11.4"\n')
    monkeypatch.chdir(tmp_path)
    main()
    result = (tmp_path / "mise.toml").read_text()
    assert dict(tomlkit.parse(result)["tools"]) == {"ruff": "0.11.4"}
    assert ".mise-desired.toml" not in os.listdir(tmp_path)


def test_merge_skips_inline_table_tool(tmp_path, monkeypatch):
    result = _run_merge(
        tmp_path,
        monkeypatch,
        '[tools]\ngo = "1.26.4"\nruff = "0.11.4"\n',
        '[tools]\ngo = { version = "1.26.4", postinstall = "echo hi" }\n\n[env]\nCOVEROUT = "cover.out"\n',
    )
    # go's inline-table pin is left untouched, no duplicate "go" key added
    assert 'go = { version = "1.26.4", postinstall = "echo hi" }' in result
    assert result.count("\ngo") == 1
    assert 'ruff = "0.11.4"' in result


def test_merge_appends_when_tools_is_last_section_no_trailing_newline(
    tmp_path,
    monkeypatch,
):
    result = _run_merge(
        tmp_path,
        monkeypatch,
        '[tools]\nruff = "0.11.4"\n',
        '[tools]\ngo = "1.26.4"',
    )
    assert dict(tomlkit.parse(result)["tools"]) == {
        "go": "1.26.4",
        "ruff": "0.11.4",
    }


def test_merge_preserves_blank_line_before_next_section(tmp_path, monkeypatch):
    result = _run_merge(
        tmp_path,
        monkeypatch,
        '[tools]\n"go:golang.org/x/vuln/cmd/govulncheck" = "1.1.4"\n',
        "[tools]\n"
        'go = "1.26.4"\n'
        'jj = "0.42.0"\n'
        '"npm:cpd" = "5.0.11"\n'
        '"go:golang.org/x/tools/cmd/deadcode" = "0.46.0"\n'
        "\n"
        "[env]\n"
        'COVEROUT = "cover.out"\n',
    )

    assert dict(tomlkit.parse(result)["tools"]) == {
        "go": "1.26.4",
        "jj": "0.42.0",
        "npm:cpd": "5.0.11",
        "go:golang.org/x/tools/cmd/deadcode": "0.46.0",
        "go:golang.org/x/vuln/cmd/govulncheck": "1.1.4",
    }
    # new tool inserted right after last existing tool, before [env]
    assert result.index("govulncheck") < result.index("[env]")
    # blank line between the tools table and the next section preserved
    assert "\n\n[env]" in result


def test_merge_preserves_comment_in_tools_section(tmp_path, monkeypatch):
    result = _run_merge(
        tmp_path,
        monkeypatch,
        '[tools]\nruff = "0.11.4"\n',
        '[tools]\n# pinned for compatibility with CI image\ngo = "1.26.4"\n',
    )
    assert "# pinned for compatibility with CI image" in result
    assert 'ruff = "0.11.4"' in result


def test_merge_ignores_unrelated_array_of_tables_section(tmp_path, monkeypatch):
    target = (
        '[tools]\ngo = "1.26.4"\n\n[[extra]]\nname = "a"\n\n[[extra]]\nname = "b"\n'
    )
    result = _run_merge(
        tmp_path,
        monkeypatch,
        '[tools]\ngo = "1.26.4"\nruff = "0.11.4"\n',
        target,
    )
    doc = tomlkit.parse(result)
    assert dict(doc["tools"]) == {"go": "1.26.4", "ruff": "0.11.4"}
    assert [dict(t) for t in doc["extra"]] == [{"name": "a"}, {"name": "b"}]


def test_merge_raises_on_invalid_desired_toml(tmp_path, monkeypatch):
    (tmp_path / ".mise-desired.toml").write_text('[tools]\ngo = "1.26.4\n')
    (tmp_path / "mise.toml").write_text("[tools]\n")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(tomlkit.exceptions.TOMLKitError):
        main()


def test_merge_raises_on_invalid_target_toml(tmp_path, monkeypatch):
    (tmp_path / ".mise-desired.toml").write_text('[tools]\nruff = "0.11.4"\n')
    (tmp_path / "mise.toml").write_text('[tools]\ngo = "1.26.4\n')
    monkeypatch.chdir(tmp_path)
    with pytest.raises(tomlkit.exceptions.TOMLKitError):
        main()
