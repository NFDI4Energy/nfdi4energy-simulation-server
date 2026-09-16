"""Incremental JSONL reader with disposable disk indexes, never task state.

Only complete object records get logical cursors. Offsets and small summaries
live in SQLite in a private temporary directory, so entity histories do not
accumulate in worker memory. Source JSONL remains authoritative.
"""
import json
import logging
import math
import sqlite3
import tempfile
import threading
import uuid
from pathlib import Path
from contextlib import contextmanager

from fastapi_app.frameworks.dacedsx.events.normalization import event_metadata, event_domain, event_instance, event_time_seconds, safe_int

logger = logging.getLogger(__name__)


def invalid_constant(value):
    raise ValueError("Non-finite JSON number: " + value)


def finite_number(raw):
    value = float(raw)
    if not math.isfinite(value):
        raise ValueError("Non-finite JSON number")
    return value


class EventStore:
    def __init__(self, max_files=64):
        self.directory = tempfile.TemporaryDirectory(prefix="simaas-events-")
        self.db = sqlite3.connect(str(Path(self.directory.name, "index.db")), check_same_thread=False)
        self.db.execute("PRAGMA cache_size=-2048")
        self.db.executescript("""
            CREATE TABLE records (
                path TEXT, position INTEGER, start INTEGER, length INTEGER,
                event_id TEXT, time REAL, step INTEGER, domain TEXT, instance TEXT,
                code TEXT, summary TEXT, time_unit TEXT, PRIMARY KEY(path, position)
            );
            CREATE INDEX event_ids ON records(path, event_id);
            CREATE INDEX event_frames ON records(path, domain, instance, position);
            CREATE INDEX event_times ON records(path, time, position);
            CREATE INDEX event_codes ON records(path, code);
        """)
        self.files = {}
        self.lock = threading.RLock()
        self.max_files = max_files
        self.bytes_read = 0

    def close(self):
        with self.lock:
            self.db.close()
            self.directory.cleanup()

    @contextmanager
    def snapshot(self, path):
        with self.lock:
            state = self._refresh(str(path))
            yield state

    def _refresh(self, path):
        try:
            stat = Path(path).stat()
            signature = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
        except FileNotFoundError:
            signature = None
        state = self.files.get(path)
        old = state["signature"] if state else None
        reset = state is None or ((old is None) != (signature is None))
        if old and signature:
            reset = old[:2] != signature[:2] or signature[2] < old[2] or (signature[2] == old[2] and signature[3] != old[3])
            if not reset and old != signature and state.get("anchor"):
                # Detect truncate-and-regrow between polls at the last indexed boundary.
                with open(path, "rb") as source:
                    source.seek(state["offset"] - len(state["anchor"]))
                    anchor = source.read(len(state["anchor"]))
                    self.bytes_read += len(anchor)
                reset = anchor != state["anchor"]
        if reset:
            self.db.execute("DELETE FROM records WHERE path=?", (path,))
            state = {"signature": None, "offset": 0, "count": 0, "anchor": b"", "generation": uuid.uuid4().hex}
            self.files.pop(path, None)
            if len(self.files) >= self.max_files:
                victim = next(iter(self.files))
                self.files.pop(victim)
                self.db.execute("DELETE FROM records WHERE path=?", (victim,))
            self.files[path] = state
        if signature is None or signature == state["signature"]:
            self.db.commit()
            return state
        # Bound the scan to the stat size so an active writer cannot monopolize it.
        with open(path, "rb") as source:
            source.seek(state["offset"])
            while source.tell() < signature[2]:
                start = source.tell()
                line = source.readline(signature[2] - start)
                self.bytes_read += len(line)
                if not line.endswith(b"\n"):
                    break
                state["offset"] = source.tell()
                state["anchor"] = line[-128:]
                try:
                    event = json.loads(line, parse_constant=invalid_constant, parse_float=finite_number)
                    if not isinstance(event, dict):
                        raise ValueError("event must be an object")
                    for field in ("id", "event_code", "category", "source", "component", "timestamp", "message"):
                        if event.get(field) is not None and not isinstance(event[field], str):
                            raise ValueError("Invalid event field: " + field)
                    metadata = event_metadata(event)
                    summary = {key: event.get(key) for key in (
                        "id", "event_code", "category", "source", "component",
                        "simulation_time", "timestamp", "progress", "message")}
                    summary["metadata"] = {key: metadata.get(key) for key in (
                        "domain", "step", "total_steps", "simulation_time_unit",
                        "instance_id", "instanceID", "wrapper_id", "attempt_id")}
                    summary["instance_id"] = event_instance(event)
                    # Charts need aggregates only; never duplicate entities in the index.
                    aggregates = metadata.get("metrics")
                    summary["metadata"]["metrics"] = aggregates if isinstance(aggregates, dict) else {}
                    self.db.execute("INSERT INTO records VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
                        path, state["count"], start, len(line), str(event.get("id") or ""),
                        event_time_seconds(event), safe_int(metadata.get("step")),
                        event_domain(event), event_instance(event), str(event.get("event_code") or ""),
                        json.dumps(summary, allow_nan=False),
                        str(metadata["simulation_time_unit"]) if metadata.get("simulation_time_unit") is not None else None))
                    state["count"] += 1
                except (ValueError, UnicodeDecodeError, TypeError):
                    logger.warning("Invalid complete JSONL record at %s:%s", path, start)
        state["signature"] = signature
        self.db.commit()
        return state

    def info(self, path):
        with self.snapshot(path) as state:
            return {"count": state["count"], "generation": state["generation"]}

    def rows(self, path, offset=0, limit=100, where="1", params=(), summaries=False, reverse=False):
        with self.snapshot(path):
            columns = "position,summary" if summaries else "position,start,length"
            order = "DESC" if reverse else "ASC"
            rows = self.db.execute(
                "SELECT " + columns + " FROM records WHERE path=? AND (" + where +
                ") ORDER BY position " + order + " LIMIT ? OFFSET ?",
                (str(path),) + tuple(params) + (limit, max(0, offset))).fetchall()
            if summaries:
                return [(row[0], json.loads(row[1])) for row in rows]
            if not rows:
                return []
            with open(path, "rb") as source:
                result = []
                for position, start, length in rows:
                    source.seek(start)
                    line = source.read(length)
                    self.bytes_read += len(line)
                    result.append((position, json.loads(line)))
                return result

    def count(self, path, where="1", params=()):
        with self.snapshot(path):
            return self.db.execute("SELECT count(*) FROM records WHERE path=? AND (" + where + ")",
                                   (str(path),) + tuple(params)).fetchone()[0]

    def page(self, path, cursor=0, limit=100, generation=None):
        with self.snapshot(path) as state:
            reset = (generation is not None and generation != state["generation"]) or cursor > state["count"]
            start = 0 if reset else max(0, cursor)
            rows = self.rows(path, start, limit)
            next_cursor = rows[-1][0] + 1 if rows else start
            return {"rows": [row for _, row in rows], "cursor": next_cursor,
                    "count": state["count"], "hasMore": next_cursor < state["count"],
                    "generation": state["generation"], "reset": reset}
