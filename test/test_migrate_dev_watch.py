"""Tests for migrate_dev_watch.py."""

from migrate_dev_watch import migrate


def _run(tmp_path, content):
    path = tmp_path / ".copier-answers.yml"
    path.write_text(content)
    migrate(str(path))
    return path.read_text()


def test_translates_dev_watch_true_to_has_executable_false(tmp_path):
    result = _run(tmp_path, "project_name: tmhi-gateway\ndev_watch: true\n")
    assert "has_executable: false" in result
    assert "dev_watch" not in result


def test_leaves_has_executable_unset_when_dev_watch_false(tmp_path):
    result = _run(tmp_path, "project_name: tmhi-cli\ndev_watch: false\n")
    assert "has_executable" not in result
    assert "dev_watch" not in result


def test_no_op_when_dev_watch_absent(tmp_path):
    content = "project_name: hrd\n"
    result = _run(tmp_path, content)
    assert result == content


def test_does_not_overwrite_existing_has_executable_answer(tmp_path):
    result = _run(
        tmp_path,
        "project_name: x\ndev_watch: true\nhas_executable: true\n",
    )
    assert result.count("has_executable") == 1
    assert "has_executable: true" in result
    assert "dev_watch" not in result


def test_missing_file_is_a_no_op(tmp_path):
    path = tmp_path / ".copier-answers.yml"
    migrate(str(path))
    assert not path.exists()


def test_idempotent_second_run_is_no_op(tmp_path):
    path = tmp_path / ".copier-answers.yml"
    path.write_text("project_name: tmhi-gateway\ndev_watch: true\n")
    migrate(str(path))
    first = path.read_text()
    migrate(str(path))
    second = path.read_text()
    assert first == second
