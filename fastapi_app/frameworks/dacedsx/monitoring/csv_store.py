"""Bounded-memory CSV frame lookup using the monitor's disposable database."""
import csv
import json
from fastapi_app.frameworks.dacedsx.events.normalization import safe_int


class CsvStore:
    def __init__(self, events):
        self.events = events
        self.signatures = {}
        self.events.db.execute("CREATE TABLE csv_rows(path TEXT, position INTEGER, step INTEGER, body TEXT, PRIMARY KEY(path, position))")
        self.events.db.execute("CREATE INDEX csv_steps ON csv_rows(path, step)")

    def _refresh(self, path):
        key = str(path)
        stat = path.stat() if path.is_file() else None
        signature = (stat.st_ino, stat.st_size, stat.st_mtime_ns) if stat else None
        if key in self.signatures and self.signatures[key][0] == signature:
            return self.signatures[key][1]
        self.events.db.execute("DELETE FROM csv_rows WHERE path=?", (key,))
        count, explicit = 0, False
        if stat:
            with open(path, newline="", encoding="utf-8") as source:
                reader = csv.DictReader(source)
                explicit = "step" in (reader.fieldnames or [])
                for count, row in enumerate(reader, 1):
                    self.events.db.execute("INSERT INTO csv_rows VALUES(?,?,?,?)",
                        (key, count - 1, safe_int(row.get("step")), json.dumps(row)))
        if key not in self.signatures and len(self.signatures) >= 16:
            victim = next(iter(self.signatures))
            self.signatures.pop(victim)
            self.events.db.execute("DELETE FROM csv_rows WHERE path=?", (victim,))
        self.signatures[key] = (signature, (count, explicit))
        self.events.db.commit()
        return count, explicit

    def info(self, path):
        with self.events.lock:
            return self._refresh(path)

    def row(self, path, index, step=None):
        with self.events.lock:
            count, explicit = self._refresh(path)
            if not count or index is None:
                return {}, False
            column, value = ("step", step) if explicit and step is not None else ("position", index)
            rows = self.events.db.execute("SELECT body FROM csv_rows WHERE path=? AND " + column + "=? LIMIT 2",
                                          (str(path), value)).fetchall()
            if len(rows) != 1:
                return {}, not explicit
            return json.loads(rows[0][0]), not explicit
