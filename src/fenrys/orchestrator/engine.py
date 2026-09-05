from __future__ import annotations

from dataclasses import dataclass, field

from fenrys.models import TaskStatus
from fenrys.planner import DeterministicPlanner
from fenrys.state import StateStore


@dataclass(slots=True)
class Orchestrator:
    """Deterministic planning only.

    Budget enforcement (tool-call and turn limits) lives in
    :class:`fenrys.policy.BudgetController`, owned per-session by
    ``InvestigationRuntime``, and is applied where tool calls actually
    happen in ``InvestigationRuntime.run_task``. Orchestrator does not
    execute tasks or call tools, so it has no budget to enforce itself.
    """

    store: StateStore
    planner: DeterministicPlanner = field(default_factory=DeterministicPlanner)

    def plan(self, session_id: str, objective: str, agent: str = "recon") -> str:
        task_id = self.store.add_task(session_id, agent, objective)
        self.store.update_state(session_id, {"objective": objective, "next_actions": [task_id]})
        return task_id

    def plan_investigation(self, session_id: str, objective: str) -> list[str]:
        """Create a deterministic recon → specialist queue before any model call."""
        task_ids: list[str] = []
        previous: list[str] = []
        for step in self.planner.make_plan(objective):
            task_id = self.store.add_task(
                session_id, step.agent, step.objective, priority=step.priority,
                dependencies=previous,
            )
            task_ids.append(task_id)
            previous = [task_id]
        self.store.update_state(session_id, {
            "objective": objective, "plan": task_ids, "next_actions": task_ids,
        })
        return task_ids

    def block_on_budget(self, task_id: str, reason: str) -> None:
        self.store.update_task(task_id, TaskStatus.BLOCKED, reason)
