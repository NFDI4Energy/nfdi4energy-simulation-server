"""Small injection contracts; importing tasks never loads a framework."""
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, FrozenSet, Optional, Protocol


@dataclass(frozen=True)
class ScenarioRequirements:
    required_resources: FrozenSet[str] = field(default_factory=frozenset)
    scenario_id: Optional[str] = None


ScenarioValidator = Callable[[Dict[str, Any]], ScenarioRequirements]
LifecycleNotifier = Callable[[str, str, Optional[str]], None]


@dataclass(frozen=True)
class StatusEvidence:
    status: str
    error: str = ""
    source: str = "task_event"


class EvidenceProvider(Protocol):
    def terminal(self, task_id: str) -> Optional[StatusEvidence]:
        ...

    def nonterminal(self, task_id: str) -> Optional[StatusEvidence]:
        ...
