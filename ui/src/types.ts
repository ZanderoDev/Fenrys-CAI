export interface JsonRpcRequest {
  jsonrpc: "2.0";
  id: number;
  method: string;
  params: Record<string, unknown>;
}

export interface JsonRpcResponse {
  jsonrpc: "2.0";
  id: number;
  result?: unknown;
  error?: { code: number; message: string };
}

export interface JsonRpcEvent {
  jsonrpc: "2.0";
  method: "event";
  params: EventParams;
}

export type EventParams =
  | { type: "token"; delta: string }
  | { type: "tool.start"; tool: string }
  | { type: "tool.end"; result: string }
  | { type: "delegate"; info: string }
  | { type: "error"; message: string }
  | { type: "response.done"; content: string; provider: string; model: string; tool_calls: number }
  | { type: "usage"; prompt_tokens?: number; completion_tokens?: number; total_tokens?: number }
  | { type: string; [key: string]: unknown };

export interface Session {
  id: string;
  target: string;
  mode: string;
  status: string;
}

export interface ChatMessage {
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  timestamp?: number;
}

export interface ToolCall {
  name: string;
  status: "running" | "ok" | "failed";
  duration_ms?: number;
  target?: string;
}

export interface AppState {
  connected: boolean;
  session_id: string | null;
  messages: ChatMessage[];
  tool_calls: ToolCall[];
  status: string;
  model: string;
  tokens_used: number;
  tokens_max: number;
  cost: number;
}
