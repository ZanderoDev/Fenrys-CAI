from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimeConfig:
    workspace: Path
    timeout_seconds: float = 30.0
    max_output_bytes: int = 64 * 1024
    max_memory_mb: int = 512
    target_networks: tuple[str, ...] = ()
    artifact_threshold_bytes: int = 32 * 1024
    max_artifact_bytes: int = 64 * 1024 * 1024

    def __post_init__(self) -> None:
        object.__setattr__(self, "workspace", self.workspace.resolve())


@dataclass(frozen=True)
class SessionConfig:
    state_dir: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "state_dir", self.state_dir.resolve())


@dataclass(frozen=True)
class LoopConfig:
    max_iterations: int = 20
    max_tool_calls: int = 12
    max_repeated_attempts: int = 0
    max_runtime_seconds: float = 300.0
    max_anti_loop_reconsiderations: int = 0
    max_provider_retries: int = 1
