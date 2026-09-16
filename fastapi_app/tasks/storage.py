"""Task-scoped filesystem access, shared by HTTP and event persistence."""
import os
import shutil
import tempfile
from pathlib import Path, PurePosixPath


class StorageError(ValueError):
    pass


def flat_filename(name):
    if not isinstance(name, str) or not name or name in {".", ".."}:
        raise StorageError("A nonempty filename is required")
    if any(char in name for char in ("/", "\\", "\x00", ":")) or any(ord(c) < 32 for c in name):
        raise StorageError("Only flat filenames are accepted")
    return name


def contained(root, relative):
    name = str(relative)
    parts = PurePosixPath(name).parts
    if not name or "\\" in name or "\x00" in name or ":" in name or PurePosixPath(name).is_absolute() or ".." in parts:
        raise StorageError("Invalid task-relative path")
    root = Path(root).resolve()
    try:
        candidate = root.joinpath(*parts).resolve()
    except RuntimeError as exc:
        raise StorageError("Invalid symbolic link in task path") from exc
    try:
        candidate.relative_to(root)
    except ValueError:
        raise StorageError("Path escapes the task directory")
    return candidate


class TaskStorage:
    def __init__(self, resources_dir, results_dir):
        self.resources_root = Path(resources_dir).resolve()
        self.results_root = Path(results_dir).resolve()

    def inputs(self, task_id):
        return self._task_root(self.resources_root, task_id)

    def results(self, task_id):
        return self._task_root(self.results_root, task_id)

    @staticmethod
    def _task_root(parent, task_id):
        name = flat_filename(task_id)
        if parent.joinpath(name).is_symlink():
            raise StorageError("Task directories cannot be symbolic links")
        return contained(parent, name)

    def input_file(self, task_id, name):
        return contained(self.inputs(task_id), name)

    def result_file(self, task_id, name):
        return contained(self.results(task_id), name)

    def stage(self):
        self.resources_root.mkdir(parents=True, exist_ok=True)
        return Path(tempfile.mkdtemp(prefix=".upload-", dir=str(self.resources_root)))

    def finalize(self, stage, task_id):
        destination = self.inputs(task_id)
        os.rename(str(stage), str(destination))
        destination.chmod(0o777)
        results = self.results(task_id)
        results.mkdir(parents=True, exist_ok=False, mode=0o777)
        results.chmod(0o777)

    def discard(self, task_id):
        for path in (self.inputs(task_id), self.results(task_id)):
            if path.exists():
                shutil.rmtree(str(path))

    def files(self, task_id):
        root = self.results(task_id)
        if not root.is_dir():
            return []
        names = []
        for directory, _, filenames in os.walk(str(root), followlinks=False):
            for name in filenames:
                if name.startswith("."):
                    continue
                relative = str(Path(directory, name).relative_to(root))
                try:
                    path = self.result_file(task_id, relative)
                    if path.is_file():
                        names.append(relative)
                except StorageError:
                    continue
        return sorted(names)
