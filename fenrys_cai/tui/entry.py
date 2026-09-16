from __future__ import annotations

import json
import sys
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

from ..config import RuntimeConfig
from ..graph import FenrysGraph
from ..llm.primary import PrimaryReasoner
from ..llm.provider import LLMProvider
from ..runtime import LocalTerminalRuntime
from ..specialists.registry import build_router
from ..tools import LocalProvider, ToolRegistry


class Gateway:
    def __init__(self) -> None:
        root = Path.cwd()
        self.workspace = root / ".fenrys-workspaces"
        self.state_dir = root / ".fenrys-state"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.runtime = LocalTerminalRuntime(RuntimeConfig(self.workspace))
        self.registry = ToolRegistry(self.runtime.artifact_store)
        self.registry.register_provider(LocalProvider(self.runtime))

    def emit(self, event: str, payload: dict) -> None:
        print(json.dumps({"event": event, "payload": payload}), flush=True)

    def handle(self, method: str, params: dict) -> dict:
        if method == "gateway.info":
            return {"name": "Fenrys-CAI", "provider_ready": LLMProvider().available}
        if method == "prompt.submit":
            session = str(params.get("session_id") or "default")
            goal = str(params.get("message") or "").strip()
            if not goal:
                raise ValueError("message is required")
            self.emit("turn.start", {"session_id": session, "goal": goal})
            with SqliteSaver.from_conn_string(str(self.state_dir / "checkpoints.sqlite")) as saver:
                graph = FenrysGraph(self.registry, PrimaryReasoner(LLMProvider()), saver,
                                    build_router(Path("prompts/specialists"), use_llm=True))
                state = None
                for step in graph.stream_turn(session, goal):
                    node = step["node"]
                    if node == "reason":
                        self.emit("reasoning.step", {key: value for key, value in step.items() if key != "node"})
                    elif node == "act":
                        self.emit("tool.complete", {key: value for key, value in step.items() if key != "node"})
                    elif node == "specialist":
                        self.emit("specialist.step", {key: value for key, value in step.items() if key != "node"})
                    elif node == "verify":
                        self.emit("verification.step", {key: value for key, value in step.items() if key != "node"})
                    elif node == "complete":
                        state = step["state"]
            if state is None:
                raise RuntimeError("stream_turn completed without a final state")
            self.emit("turn.complete", {"state": state.export()})
            return {"completed": state.completed, "history": state.history[-1:]}
        if method == "session.resume":
            session = str(params.get("session_id") or "default")
            with SqliteSaver.from_conn_string(str(self.state_dir / "checkpoints.sqlite")) as saver:
                graph = FenrysGraph(self.registry, PrimaryReasoner(LLMProvider()), saver)
                state = graph.resume(session)
            return {"state": state.export()}
        raise ValueError(f"unknown method: {method}")


def main() -> None:
    gateway = Gateway()
    gateway.emit("gateway.ready", gateway.handle("gateway.info", {}))
    for line in sys.stdin:
        try:
            request = json.loads(line)
            result = gateway.handle(request["method"], request.get("params", {}))
            print(json.dumps({"id": request.get("id"), "result": result}), flush=True)
        except Exception as exc:
            print(json.dumps({"id": request.get("id") if "request" in locals() else None,
                              "error": {"message": str(exc)}}), flush=True)


if __name__ == "__main__":
    main()
