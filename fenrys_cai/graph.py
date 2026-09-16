from __future__ import annotations

import os
import time
from dataclasses import asdict
from typing import Annotated, Any, Iterator, Protocol, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from operator import add

from .config import LoopConfig
from .llm.provider import LLMError
from .llm.primary import PrimaryDecision
from .hypotheses import Hypothesis, HypothesisEngine, HypothesisStatus, Verification, VerificationStatus
from .models import Attempt, DeadEnd, ToolResult
from .specialists.base import SpecialistRequest, bounded_context
from .specialists.router import SpecialistRouter
from .state import CyberState
from .tools import ToolRegistry
from .verification import match_observation
from .targets import Endpoint, Host, Service


class Reasoner(Protocol):
    def decide(self, state: CyberState, tools: list[Any]) -> PrimaryDecision: ...


# Backward-compatible alias for existing test fixtures.
Decision = PrimaryDecision


def _merge_records(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = {item["id"]: item for item in left}
    for item in right:
        merged[item["id"]] = item
    return list(merged.values())


class GraphState(TypedDict, total=False):
    session_id: str
    goal: str
    scope: str
    phase: str
    findings: Annotated[list[dict[str, Any]], add]
    hypotheses: Annotated[list[dict[str, Any]], _merge_records]
    verifications: Annotated[list[dict[str, Any]], _merge_records]
    attempts: Annotated[list[dict[str, Any]], add]
    evidence: Annotated[list[dict[str, Any]], add]
    artifacts: Annotated[list[str], add]
    history: Annotated[list[str], add]
    flags: Annotated[list[str], add]
    completed: bool
    decision: dict[str, Any] | None
    halt_reason: str | None
    specialist: dict[str, Any] | None
    specialist_depth: int
    dead_ends: Annotated[list[dict[str, Any]], _merge_records]
    iteration_count: int
    tool_call_count: int
    started_at: float
    progress_markers: Annotated[list[str], add]
    anti_loop_reconsiderations: int
    provider_retry_count: int
    last_provider_error: str
    hosts: Annotated[list[dict[str, Any]], _merge_records]
    services: Annotated[list[dict[str, Any]], _merge_records]
    endpoints: Annotated[list[dict[str, Any]], _merge_records]
    technologies: Annotated[list[str], add]


def _cyber_state(state: GraphState) -> CyberState:
    return CyberState(session_id=state["session_id"], goal=state["goal"], scope=state.get("scope", "authorized CTF/lab only"),
        phase=state.get("phase", "RECON"), findings=list(state.get("findings", [])), hypotheses=[Hypothesis.from_dict(item) for item in state.get("hypotheses", [])],
        verifications=[Verification.from_dict(item) for item in state.get("verifications", [])],
        attempts=[Attempt(**attempt) for attempt in state.get("attempts", [])], evidence=list(state.get("evidence", [])),
        artifacts=list(state.get("artifacts", [])), history=list(state.get("history", [])), flags=list(state.get("flags", [])), completed=state.get("completed", False),
        dead_ends=[DeadEnd(**item) for item in state.get("dead_ends", [])], iteration_count=state.get("iteration_count", 0),
        tool_call_count=state.get("tool_call_count", 0), started_at=state.get("started_at", time.time()), progress_markers=list(state.get("progress_markers", [])),
        anti_loop_reconsiderations=state.get("anti_loop_reconsiderations", 0),
        provider_retry_count=state.get("provider_retry_count", 0), last_provider_error=state.get("last_provider_error", ""),
        hosts=[Host(**item) for item in state.get("hosts", [])], services=[Service(**item) for item in state.get("services", [])],
        endpoints=[Endpoint(**item) for item in state.get("endpoints", [])], technologies=list(state.get("technologies", [])))


class FenrysGraph:
    """A genuine LangGraph StateGraph with reasoning as a loop node."""
    def __init__(self, registry: ToolRegistry, reasoner: Reasoner, checkpointer: BaseCheckpointSaver | None = None, specialist_router: SpecialistRouter | None = None, loop_config: LoopConfig | None = None) -> None:
        self.registry, self.reasoner, self.specialist_router = registry, reasoner, specialist_router
        self.loop_config = loop_config or LoopConfig()
        self.checkpointer = checkpointer or InMemorySaver()
        graph = StateGraph(GraphState)
        graph.add_node("reason", self._reason)
        graph.add_node("specialist", self._specialist)
        graph.add_node("verify", self._verify)
        graph.add_node("act", self._act)
        graph.add_edge(START, "reason")
        graph.add_conditional_edges("reason", self._after_reason, {"reason": "reason", "act": "act", "specialist": "specialist", "verify": "verify", "end": END})
        graph.add_edge("specialist", "reason")
        graph.add_edge("act", "reason")
        graph.add_edge("verify", "reason")
        self.app = graph.compile(checkpointer=self.checkpointer)

    def _reason(self, state: GraphState) -> GraphState:
        iteration = int(state.get("iteration_count", 0)) + 1
        if iteration > self.loop_config.max_iterations:
            return {"completed": True, "halt_reason": "iteration_limit", "history": ["Iteration limit reached"], "iteration_count": iteration}
        if time.time() - float(state.get("started_at", time.time())) > self.loop_config.max_runtime_seconds:
            return {"completed": True, "halt_reason": "runtime_limit", "history": ["Runtime limit reached"], "iteration_count": iteration}
        try:
            decision = self.reasoner.decide(_cyber_state(state), self.registry.discover())
        except LLMError as exc:
            retryable = {"timeout", "connection_failure", "provider_error", "rate_limited"}
            retries = int(state.get("provider_retry_count", 0))
            if exc.code in retryable and retries < self.loop_config.max_provider_retries:
                return {"completed": False, "decision": None, "history": [f"Provider retry scheduled: {exc.code}"],
                        "iteration_count": iteration, "provider_retry_count": retries + 1, "last_provider_error": exc.code}
            return {"completed": True, "halt_reason": "provider_failure", "history": [f"Reasoner failure: {exc.code}"],
                    "iteration_count": iteration, "provider_retry_count": retries, "last_provider_error": exc.code}
        except Exception as exc:
            return {"completed": True, "halt_reason": "model_failure", "history": [f"Reasoner failure: {exc}"], "iteration_count": iteration}
        retry_update = {"provider_retry_count": 0, "last_provider_error": ""} if state.get("provider_retry_count", 0) else {}
        if decision.kind == "stop" or decision.complete:
            return {"completed": True, "decision": None, "halt_reason": "goal_achieved", "history": [decision.rationale or "Reasoner completed objective"], "iteration_count": iteration, **retry_update}
        if decision.kind == "specialist" and decision.specialist:
            return {"decision": {"tool": "__specialist__", "arguments": {"domain": decision.specialist}, "rationale": decision.rationale}, "iteration_count": iteration, **retry_update}
        if decision.kind == "tool" and decision.tool and decision.arguments is not None:
            return {"decision": {"tool": decision.tool, "arguments": decision.arguments, "rationale": decision.rationale}, "iteration_count": iteration, **retry_update}
        if decision.kind == "hypothesis" and decision.hypothesis:
            proposal = decision.hypothesis
            hypothesis = HypothesisEngine.create(
                proposal["statement"], proposal["domain"], decision.confidence,
                proposal["required_evidence"], state["goal"], related_target=str(proposal.get("related_target", "")),
                provenance={"source": "primary_reasoner"},
            )
            return {"hypotheses": [hypothesis.to_dict()], "decision": None, "history": [f"hypothesis:{hypothesis.id}:proposed"], "iteration_count": iteration, "progress_markers": [f"hypothesis:{hypothesis.id}"], **retry_update}
        if decision.kind == "verify" and decision.verification:
            return {"decision": {"tool": "__verify__", "arguments": decision.verification, "rationale": decision.rationale}, "iteration_count": iteration, **retry_update}
        # continue — loop back to reason
        return {"decision": None, "history": [decision.rationale or "Reasoner continuing"], "iteration_count": iteration, **retry_update}

    def _after_reason(self, state: GraphState) -> str:
        if state.get("completed", False):
            return "end"
        decision = state.get("decision") or {}
        if decision.get("tool") == "__specialist__":
            return "specialist"
        if decision.get("tool") == "__verify__":
            return "verify"
        if decision.get("tool"):
            return "act"
        return "reason"

    def _verify(self, state: GraphState) -> GraphState:
        arguments = (state.get("decision") or {}).get("arguments", {})
        cyber = _cyber_state(state)
        try:
            hypothesis = cyber.hypothesis(str(arguments["hypothesis_id"]))
            if hypothesis.status in {HypothesisStatus.PROPOSED, HypothesisStatus.INCONCLUSIVE}:
                HypothesisEngine.transition(hypothesis, HypothesisStatus.TESTING)
            verification = HypothesisEngine.create_verification(
                hypothesis, str(arguments["method"]), str(arguments["expected_observation"]),
                provenance={"source": "primary_reasoner"},
            )
            HypothesisEngine.transition_verification(verification, VerificationStatus.IN_PROGRESS)
            actual = arguments.get("actual_observation")
            evidence_id = arguments.get("evidence_id")
            if actual is not None:
                expected = arguments["expected_observation"]
                match = match_observation(expected, actual) if isinstance(expected, dict) else None
                if match is not None and match.matched is not None:
                    conclusion = VerificationStatus.CONFIRMED if match.matched else VerificationStatus.FAILED
                    if evidence_id:
                        (verification.supporting_evidence if match.matched else verification.contradicting_evidence).append(str(evidence_id))
                    HypothesisEngine.transition_verification(verification, conclusion, actual_observation=match.observation, confidence=1.0)
                    HypothesisEngine.conclude(hypothesis, verification)
                elif match is not None:
                    HypothesisEngine.transition_verification(verification, VerificationStatus.INCONCLUSIVE, actual_observation=match.observation)
                    HypothesisEngine.conclude(hypothesis, verification)
        except (KeyError, ValueError) as exc:
            return {"completed": True, "halt_reason": "verification_failure", "history": [f"Verification failure: {exc}"]}
        # Creating a verification never confirms it. Evidence must be collected and evaluated later.
        return {"hypotheses": [hypothesis.to_dict()], "verifications": [verification.to_dict()],
                "decision": None, "history": [f"verification:{verification.id}:{verification.status.value}"],
                "progress_markers": [f"verification:{verification.id}:{verification.status.value}"]}

    def _specialist(self, state: GraphState) -> GraphState:
        if self.specialist_router is None:
            return {"completed": True, "halt_reason": "specialist_unavailable", "history": ["Specialist requested but no router is configured"]}
        decision = state["decision"]
        arguments = dict(decision.get("arguments", {}))
        cyber = _cyber_state(state)
        depth = int(state.get("specialist_depth", 0))
        request = SpecialistRequest(str(arguments.get("domain", "verification")), cyber.goal, cyber.scope, cyber.phase,
            bounded_context(cyber), tuple(self.registry.discover()), depth)
        response = self.specialist_router.reason(request)
        specialist_record = {"domain": response.domain, "kind": response.decision.kind, "rationale": response.decision.rationale,
            "confidence": response.decision.confidence, "verification_needed": response.decision.verification_needed,
            "delegate_to": response.decision.delegate_to, "depth": depth + 1}
        history = [f"specialist:{response.domain}:{response.decision.kind}"]
        hypothesis_updates = []
        for statement in response.hypotheses[:5]:
            proposal = HypothesisEngine.create(
                statement, response.domain, response.decision.confidence,
                list(response.evidence_requirements), cyber.goal,
                provenance={"source": "specialist", "domain": response.domain},
            )
            hypothesis_updates.append(proposal.to_dict())
        if response.decision.kind == "tool" and response.decision.tool and response.decision.arguments is not None:
            return {"specialist": specialist_record, "specialist_depth": depth + 1, "hypotheses": hypothesis_updates,
                    "decision": {"tool": response.decision.tool, "arguments": response.decision.arguments, "rationale": response.decision.rationale}, "history": history}
        if response.decision.kind == "delegate" and response.decision.delegate_to:
            if depth + 1 > self.specialist_router.max_depth:
                return {"completed": True, "halt_reason": "specialist_depth", "specialist": specialist_record, "history": ["Specialist delegation depth limit reached"]}
            return {"specialist": specialist_record, "specialist_depth": depth + 1, "hypotheses": hypothesis_updates,
                    "decision": {"tool": "__specialist__", "arguments": {"domain": response.decision.delegate_to}, "rationale": response.decision.rationale}, "history": history}
        return {"specialist": specialist_record, "specialist_depth": depth + 1, "hypotheses": hypothesis_updates, "decision": None, "history": history}

    def _act(self, state: GraphState) -> GraphState:
        tool_count = int(state.get("tool_call_count", 0))
        if tool_count >= self.loop_config.max_tool_calls:
            return {"completed": True, "halt_reason": "tool_call_limit", "history": ["Tool call limit reached"]}
        decision = state["decision"]
        arguments = decision.get("arguments", {})
        tool_name = decision.get("tool", "")
        rationale = decision.get("rationale", "")
        hypothesis_id = arguments.pop("hypothesis_id", None)
        cyber = _cyber_state(state)
        before_progress = cyber.progress_signature()
        attempt = Attempt(state["goal"], str(arguments.get("target", "local")), tool_name, arguments, rationale, "pending",
                          hypothesis_id=hypothesis_id, progress_token=before_progress)
        duplicate_count = sum(1 for item in cyber.attempts if item.fingerprint == attempt.fingerprint)
        if duplicate_count > self.loop_config.max_repeated_attempts:
            evidence_refs = [item.get("id", "") for item in cyber.evidence[-5:]]
            dead_end = DeadEnd(state["goal"], attempt.target, "Repeated attempt without meaningful state change",
                               [item.id for item in cyber.attempts if item.fingerprint == attempt.fingerprint], evidence_refs,
                               [hypothesis_id] if hypothesis_id else [], ["change parameters", "change strategy", "collect new evidence"])
            reconsiderations = int(state.get("anti_loop_reconsiderations", 0))
            if reconsiderations < self.loop_config.max_anti_loop_reconsiderations:
                return {"completed": False, "decision": None, "dead_ends": [asdict(dead_end)],
                        "anti_loop_reconsiderations": reconsiderations + 1,
                        "history": ["Anti-loop blocked repeated action; choose a materially different strategy"]}
            return {"completed": True, "halt_reason": "anti_loop", "dead_ends": [asdict(dead_end)],
                    "history": ["Anti-loop blocked materially identical action"]}
        result = self.registry.invoke(tool_name, arguments)
        attempt.result = result.status
        cyber.observe(result)
        attempt.evidence_references = [cyber.evidence[-1]["id"]]
        progress_marker = cyber.progress_signature()
        attempt.progress_token = progress_marker
        if hypothesis_id:
            try:
                hypothesis = cyber.hypothesis(hypothesis_id)
                if attempt.id not in hypothesis.test_attempts:
                    hypothesis.test_attempts.append(attempt.id)
                hypothesis_updates = [hypothesis.to_dict()]
            except ValueError:
                hypothesis_updates = []
        else:
            hypothesis_updates = []
        return {"attempts": [asdict(attempt)], "evidence": cyber.evidence[-1:], "artifacts": result.artifacts,
                "history": [f"{result.tool}: {result.status}"], "decision": None, "tool_call_count": tool_count + 1,
                "progress_markers": [progress_marker] if progress_marker != before_progress else [], "hypotheses": hypothesis_updates}

    @staticmethod
    def initial_state(state: CyberState) -> GraphState:
        data = state.export()
        return data | {"decision": None, "halt_reason": None, "specialist": None, "specialist_depth": 0}

    def run(self, state: CyberState, max_steps: int = 20, *, interrupt_after: list[str] | None = None) -> CyberState:
        limit = min(max_steps, self.loop_config.max_iterations)
        config = {"configurable": {"thread_id": state.session_id}, "recursion_limit": limit * 4 + 4}
        final = self.app.invoke(self.initial_state(state), config, interrupt_after=interrupt_after)
        return _cyber_state(final)

    def _turn_input(self, session_id: str, message: str, max_steps: int) -> tuple[GraphState, dict[str, Any]]:
        """Build a fresh input or a per-turn delta without replacing session memory."""
        limit = min(max_steps, self.loop_config.max_iterations)
        config = {"configurable": {"thread_id": session_id}, "recursion_limit": limit * 4 + 4}
        if not self.app.get_state(config).values:
            return self.initial_state(CyberState(session_id, message)), config
        return {
            "history": [f"user_directive: {message}"],
            "decision": None,
            "halt_reason": None,
            "completed": False,
            "iteration_count": 0,
            "tool_call_count": 0,
            "started_at": time.time(),
            "provider_retry_count": 0,
            "last_provider_error": "",
            "anti_loop_reconsiderations": 0,
            "specialist_depth": 0,
        }, config

    def continue_session(self, session_id: str, message: str, max_steps: int = 20) -> CyberState:
        """Continue a session while retaining cumulative engagement state and attempts."""
        graph_input, config = self._turn_input(session_id, message, max_steps)
        return _cyber_state(self.app.invoke(graph_input, config))

    @staticmethod
    def _stream_event(node: str, update: GraphState) -> dict[str, Any]:
        if node == "reason":
            return {"node": node, "rationale": (update.get("history") or [""])[-1], "phase": update.get("phase")}
        if node == "act":
            attempt = (update.get("attempts") or [{}])[-1]
            return {"node": node, "tool": attempt.get("tool", ""), "result": attempt.get("result", "")}
        if node == "specialist":
            specialist = update.get("specialist") or {}
            return {"node": node, "domain": specialist.get("domain", ""), "kind": specialist.get("kind", "")}
        if node == "verify":
            verification = (update.get("verifications") or [{}])[-1]
            return {"node": node, "verification_id": verification.get("id", ""), "status": verification.get("status", "")}
        return {"node": node}

    def stream_turn(self, session_id: str, message: str, max_steps: int = 20) -> Iterator[dict[str, Any]]:
        """Yield each node update for a turn, followed by its resolved CyberState."""
        graph_input, config = self._turn_input(session_id, message, max_steps)
        for update in self.app.stream(graph_input, config, stream_mode="updates"):
            for node, values in update.items():
                yield self._stream_event(node, values)
        yield {"node": "complete", "state": _cyber_state(self.app.get_state(config).values)}

    def resume(self, session_id: str, max_steps: int = 20) -> CyberState:
        config = {"configurable": {"thread_id": session_id}, "recursion_limit": max_steps * 2 + 2}
        snapshot = self.app.get_state(config)
        if not snapshot.values:
            raise ValueError(f"No LangGraph checkpoint for session {session_id!r}")
        restored = _cyber_state(snapshot.values)
        if restored.completed:
            return restored
        return _cyber_state(self.app.invoke(None, config))
