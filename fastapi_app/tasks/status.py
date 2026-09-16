"""Redis and stored task status, with optional framework-owned evidence."""
from typing import Optional
from fastapi_app.tasks.contracts import EvidenceProvider

VALID_STATUSES = {"PENDING", "RUNNING", "DONE", "ERROR", "UNKNOWN"}


class StatusService:
    def __init__(self, redis_client, evidence_provider: Optional[EvidenceProvider] = None):
        self.redis = redis_client
        self.evidence = evidence_provider

    def resolve(self, task_id, stored_status=None, stored_error=None):
        available = True
        try:
            raw = self.redis.hgetall("task:" + task_id)
        except Exception:
            raw, available = {}, False
        values = {(k.decode(errors="replace") if isinstance(k, bytes) else k):
                  (v.decode(errors="replace") if isinstance(v, bytes) else v) for k, v in raw.items()}
        if values.get("status") in VALID_STATUSES:
            return self._result(values["status"], values.get("error", ""), "redis", available)
        terminal = self.evidence.terminal(task_id) if self.evidence is not None else None
        if terminal is not None:
            return self._result(terminal.status, terminal.error, terminal.source, available)
        if stored_status in {"RUNNING", "DONE", "ERROR", "UNKNOWN"}:
            return self._result(stored_status, stored_error or "", "database", available)
        pending = self.evidence.nonterminal(task_id) if self.evidence is not None else None
        if pending is not None:
            return self._result(pending.status, pending.error, pending.source, available)
        return self._result("UNKNOWN", "", "unavailable", available)

    @staticmethod
    def _result(status, error, source, available):
        return {"status": status, "error": error, "statusSource": source,
                "redisAvailable": available}
