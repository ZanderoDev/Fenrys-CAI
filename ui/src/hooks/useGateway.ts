import { useState, useEffect, useCallback, useRef } from "react";
import { GatewayClient } from "../gateway/client.js";
import type { EventParams, ChatMessage, ToolCall } from "../types.js";

const PYTHON_PATH = process.env.FENRYS_PYTHON || "python3";
const GATEWAY_MODULE = "fenrys.gateway";

export interface UseGatewayReturn {
  connected: boolean;
  session_id: string | null;
  messages: ChatMessage[];
  tool_calls: ToolCall[];
  status: string;
  model: string;
  tokens_used: number;
  tokens_max: number;
  cost: number;
  sendPrompt: (text: string) => void;
  newSession: (target?: string, mode?: string) => Promise<void>;
  clearMessages: () => void;
}

export function useGateway(): UseGatewayReturn {
  const [connected, setConnected] = useState(false);
  const [session_id, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [toolCalls, setToolCalls] = useState<ToolCall[]>([]);
  const [status, setStatus] = useState("connecting");
  const [model, setModel] = useState("minimax/minimax-m3:free");
  const [tokensUsed, setTokensUsed] = useState(0);
  const [tokensMax] = useState(128000);
  const [cost, setCost] = useState(0);

  const clientRef = useRef<GatewayClient | null>(null);

  useEffect(() => {
    const client = new GatewayClient(PYTHON_PATH, GATEWAY_MODULE);
    clientRef.current = client;

    client.on("event", (event: EventParams) => {
      switch (event.type) {
        case "token":
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last && last.role === "assistant") {
              return [...prev.slice(0, -1), { ...last, content: last.content + event.delta }];
            }
            return [...prev, { role: "assistant", content: String(event.delta), timestamp: Date.now() }];
          });
          break;

        case "tool.start":
          setToolCalls((prev) => [
            ...prev,
            { name: String(event.tool), status: "running" as const, target: "" },
          ]);
          setStatus(`running ${event.tool}`);
          break;

        case "tool.end":
          setToolCalls((prev) => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            if (last && last.status === "running") {
              updated[updated.length - 1] = { ...last, status: "ok" };
            }
            return updated;
          });
          setStatus("thinking");
          break;

        case "delegate":
          setStatus(`delegating ${event.info}`);
          break;

        case "error":
          setMessages((prev) => [
            ...prev,
            { role: "system", content: `Error: ${event.message}`, timestamp: Date.now() },
          ]);
          break;

        case "response.done":
          if (event.model) setModel(String(event.model));
          setStatus("ready");
          break;

        case "usage":
          if (event.total_tokens) setTokensUsed(Number(event.total_tokens));
          break;
      }
    });

    client.on("exit", () => {
      setConnected(false);
      setStatus("disconnected");
    });

    client.on("stderr", (text: string) => {
      // Log stderr for debugging
      console.error("[fenrys]", text);
    });

    // Auto-create session
    client
      .newSession()
      .then((result) => {
        setSessionId(result.session_id);
        setConnected(true);
        setStatus("ready");
      })
      .catch(() => {
        setStatus("failed to connect");
      });

    return () => {
      client.kill();
    };
  }, []);

  const sendPrompt = useCallback(
    (text: string) => {
      if (!clientRef.current || !session_id) return;
      setMessages((prev) => [...prev, { role: "user", content: text, timestamp: Date.now() }]);
      setToolCalls([]);
      setStatus("thinking");
      clientRef.current.sendPrompt(text, session_id);
    },
    [session_id]
  );

  const newSession = useCallback(async (target?: string, mode?: string) => {
    if (!clientRef.current) return;
    const result = await clientRef.current.newSession(target, mode);
    setSessionId(result.session_id);
    setMessages([]);
    setToolCalls([]);
    setStatus("ready");
  }, []);

  const clearMessages = useCallback(() => {
    setMessages([]);
    setToolCalls([]);
  }, []);

  return {
    connected,
    session_id,
    messages,
    tool_calls: toolCalls,
    status,
    model,
    tokens_used: tokensUsed,
    tokens_max: tokensMax,
    cost,
    sendPrompt,
    newSession,
    clearMessages,
  };
}
