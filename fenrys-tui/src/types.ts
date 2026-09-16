/**
 * Kontrak wire Fenrys-CAI — persis seperti yang di-emit gateway Python
 * (fenrys_cai/tui/entry.py). Jangan menambah field yang tidak di-produce core.
 */

export type SessionId = string

/** state.export() dari CyberState — sudah diredaksi oleh DEFAULT_REDACTOR. */
export interface Hypothesis {
  id: string
  statement: string
  domain: string
  confidence: number
  status:
    | 'proposed'
    | 'testing'
    | 'supported'
    | 'confirmed'
    | 'refuted'
    | 'inconclusive'
    | 'superseded'
  required_evidence: string[]
  supporting_evidence: string[]
  contradicting_evidence: string[]
  related_objective: string
  related_target: string
  test_attempts: string[]
  verification_state: 'pending' | 'in_progress' | 'confirmed' | 'failed' | 'inconclusive'
  created_at: number
  updated_at: number
}

export interface Verification {
  id: string
  hypothesis_id: string
  method: string
  status: 'pending' | 'in_progress' | 'confirmed' | 'failed' | 'inconclusive'
  expected_observation: unknown
  actual_observation: string
  supporting_evidence: string[]
  contradicting_evidence: string[]
  confidence: number
  timestamp: number
}

export interface Attempt {
  id: string
  objective: string
  target: string
  tool: string
  parameters: Record<string, unknown>
  strategy: string
  result: string
  timestamp: number
  hypothesis_id: string | null
  evidence_references: string[]
  progress_token: string
}

export interface Host {
  id: string
  address: string
  hostname: string
  os_fingerprint: string
  status: string
  evidence: string[]
  confidence: number
  first_seen: number
  updated_at: number
}

export interface Service {
  id: string
  host_id: string
  port: number
  protocol: string
  service: string
  version: string
  state: string
  confidence: number
  evidence: string[]
}

export interface Endpoint {
  id: string
  url: string
  method: string
  host_id: string
  status_observation: unknown
  technologies: string[]
  evidence: string[]
  confidence: number
}

export interface DeadEnd {
  id: string
  objective: string
  target: string
  reason: string
  blocked_attempts: string[]
  relevant_evidence: string[]
  hypotheses: string[]
  suggested_alternatives: string[]
  timestamp: number
}

export interface CyberStateExport {
  session_id: string
  goal: string
  scope: string
  phase: string
  findings: unknown[]
  hypotheses: Hypothesis[]
  verifications: Verification[]
  attempts: Attempt[]
  evidence: Array<{id: string; tool: string; status: string; provenance: unknown}>
  artifacts: string[]
  history: string[]
  flags: string[]
  completed: boolean
  halt_reason: string | null
  dead_ends: DeadEnd[]
  iteration_count: number
  tool_call_count: number
  started_at: number
  progress_markers: string[]
  anti_loop_reconsiderations: number
  provider_retry_count: number
  last_provider_error: string
  hosts: Host[]
  services: Service[]
  endpoints: Endpoint[]
  technologies: string[]
}

export interface GatewayInfo {
  name: string
  provider_ready: boolean
}

/** Peta event -> payload persis seperti _stream_event gateway. */
export interface EventPayloads {
  'gateway.ready': GatewayInfo
  'turn.start': {session_id: string; goal: string}
  'reasoning.step': {rationale: string; phase: string | null}
  'tool.complete': {tool: string; result: string}
  'specialist.step': {domain: string; kind: string}
  'verification.step': {verification_id: string; status: string}
  'turn.complete': {state: CyberStateExport}
}

export type EventName = keyof EventPayloads

export interface GatewayEvent<N extends EventName = EventName> {
  event: N
  payload: EventPayloads[N]
}

export interface PromptSubmitResult {
  completed: boolean
  history: string[]
}

export interface SessionResumeResult {
  state: CyberStateExport
}

/** Frame mentah NDJSON dari/ke gateway. */
export type RequestFrame = {
  id: number | null
  method: string
  params?: Record<string, unknown>
}
export type ResponseFrame =
  | {id: number | null; result: unknown}
  | {id: number | null; error: {message: string}}
