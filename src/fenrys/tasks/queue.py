from __future__ import annotations

from fenrys.models import TaskStatus
from fenrys.state import StateStore


class TaskQueue:
    def __init__(self, store: StateStore, session_id: str):
        self.store = store
        self.session_id = session_id

    def next_ready(self) -> dict | None:
        tasks = self.store.list_tasks(self.session_id)
        for task in tasks:
            if task["status"] == TaskStatus.QUEUED.value:
                return task
        return None
