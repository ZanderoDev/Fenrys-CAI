import argparse
import json
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

from .config import RuntimeConfig
from .graph import FenrysGraph
from .llm.primary import PrimaryReasoner
from .llm.provider import LLMProvider
from .runtime import LocalTerminalRuntime
from .specialists.registry import build_router
from .state import CyberState
from .tools import LocalProvider, ToolRegistry


def main() -> None:
    parser = argparse.ArgumentParser(prog="fenrys", description="Fenrys-CAI authorized CTF/lab agent")
    parser.add_argument("goal", nargs="?", default="Run local runtime demonstration")
    parser.add_argument("--workspace", type=Path, default=Path.cwd() / ".fenrys-workspaces")
    parser.add_argument("--state-dir", type=Path, default=Path.cwd() / ".fenrys-state")
    parser.add_argument("--session", default="default")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--specialist", action="store_true", help="Enable specialist reasoning")
    args = parser.parse_args()
    runtime = LocalTerminalRuntime(RuntimeConfig(args.workspace))
    registry = ToolRegistry()
    registry.register_provider(LocalProvider(runtime))
    provider = LLMProvider()
    reasoner = PrimaryReasoner(provider)
    router = build_router(Path("prompts/specialists"), use_llm=True) if args.specialist else None
    args.state_dir.mkdir(parents=True, exist_ok=True)
    with SqliteSaver.from_conn_string(str(args.state_dir / "checkpoints.sqlite")) as saver:
        graph = FenrysGraph(registry, reasoner, saver, specialist_router=router)
        final = graph.resume(args.session) if args.resume else graph.run(CyberState(args.session, args.goal))
    print(json.dumps(final.export(), indent=2))


if __name__ == "__main__": main()
