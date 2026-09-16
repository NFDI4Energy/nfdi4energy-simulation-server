"""DaceDSX task evidence; wrapper events never imply whole-task completion."""
from fastapi_app.tasks.contracts import StatusEvidence

TERMINAL_CODES = ("TASK_COMPLETED", "TASK_FAILED")


class EventEvidence:
    def __init__(self, storage, events):
        self.storage, self.events = storage, events

    def terminal(self, task_id):
        path = self.storage.result_file(task_id, "events/structured_events.jsonl")
        terminals = self.events.rows(path, limit=2, where="code IN (?,?)",
                                    params=TERMINAL_CODES, summaries=True, reverse=True)
        done = self.events.count(path, "code=?", ("TASK_COMPLETED",))
        failed = self.events.count(path, "code=?", ("TASK_FAILED",))
        if done and failed:
            return StatusEvidence("UNKNOWN", "Conflicting task completion evidence", "conflicting_events")
        if terminals:
            event = terminals[0][1]
            if event.get("event_code") == "TASK_COMPLETED":
                return StatusEvidence("DONE")
            return StatusEvidence("ERROR", event.get("message") or "")
        return None

    def nonterminal(self, task_id):
        path = self.storage.result_file(task_id, "events/structured_events.jsonl")
        pending = self.events.count(path, "code IN ('TASK_STARTED','TASK_RECEIVED','TASK_ACCEPTED','TASK_QUEUED')")
        if pending:
            started = self.events.count(path, "code='TASK_STARTED'")
            return StatusEvidence("RUNNING" if started else "PENDING")
        return None
