"""Task-scoped filesystem access must never leave the task directory."""
import os

import pytest

from fastapi_app.tasks.storage import StorageError, TaskStorage, contained, flat_filename


@pytest.mark.parametrize("name", ["scenario.json", "grid-v2.csv", "a b.txt"])
def test_flat_filename_accepts_plain_names(name):
    assert flat_filename(name) == name


@pytest.mark.parametrize("name", ["", ".", "..", "a/b", "a\\b", "c:x", "a\x00b", "a\nb", None, 3])
def test_flat_filename_rejects_paths_and_control_characters(name):
    with pytest.raises(StorageError):
        flat_filename(name)


def test_contained_resolves_inside_root(tmp_path):
    (tmp_path / "sub").mkdir()
    assert contained(tmp_path, "sub/file.txt") == (tmp_path / "sub" / "file.txt").resolve()


@pytest.mark.parametrize("relative", ["../x", "a/../../x", "/etc/passwd", "a\\b", "c:x", ""])
def test_contained_rejects_escapes(tmp_path, relative):
    with pytest.raises(StorageError):
        contained(tmp_path, relative)


def test_contained_rejects_symlink_escape(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "root"
    root.mkdir()
    os.symlink(outside, root / "link")
    with pytest.raises(StorageError, match="escapes"):
        contained(root, "link/file.txt")


def test_task_storage_roots_and_files(tmp_path):
    storage = TaskStorage(tmp_path / "resources", tmp_path / "results")
    stage = storage.stage()
    (stage / "scenario.json").write_text("{}")
    storage.finalize(stage, "task-1")
    assert storage.inputs("task-1").is_dir()
    assert storage.results("task-1").is_dir()
    assert storage.files("task-1") == []

    results = storage.results("task-1")
    (results / "out.csv").write_text("1")
    (results / ".hidden").write_text("1")
    (results / "nested").mkdir()
    (results / "nested" / "plot.png").write_bytes(b"\x89PNG")
    assert storage.files("task-1") == ["nested/plot.png", "out.csv"]

    storage.discard("task-1")
    assert not storage.inputs("task-1").exists()
    assert not storage.results("task-1").exists()


def test_task_storage_rejects_bad_task_ids(tmp_path):
    storage = TaskStorage(tmp_path / "resources", tmp_path / "results")
    for task_id in ("../x", "a/b", ""):
        with pytest.raises(StorageError):
            storage.inputs(task_id)
    with pytest.raises(StorageError):
        storage.result_file("task-1", "../secret")
