import React, { useState, useMemo } from "react";
import { Box, Text, useInput, useApp } from "ink";
import TextInput from "ink-text-input";
import { StatusBar } from "./StatusBar.js";
import { ChatPane } from "./ChatPane.js";
import { ToolTree } from "./ToolTree.js";
import { getTheme, type ThemeColors } from "../theme/engine.js";
import { createSlashCommands, matchSlashCommand, getHelpText } from "../hooks/useSlashCommands.js";
import type { ChatMessage, ToolCall } from "../types.js";

interface AppLayoutProps {
  connected: boolean;
  session_id: string | null;
  messages: ChatMessage[];
  tool_calls: ToolCall[];
  status: string;
  model: string;
  tokens_used: number;
  tokens_max: number;
  cost: number;
  onsubmit: (text: string) => void;
  onClear?: () => void;
  onNewSession?: (target?: string) => void;
  addMessage?: (msg: ChatMessage) => void;
}

export function AppLayout({
  connected,
  session_id,
  messages,
  tool_calls,
  status,
  model,
  tokens_used,
  tokens_max,
  cost,
  onsubmit,
  onClear,
  onNewSession,
  addMessage,
}: AppLayoutProps): React.ReactElement {
  const [input, setInput] = useState("");
  const [history, setHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState(-1);
  const { exit } = useApp();
  const { theme, colors } = useMemo(() => getTheme(), []);

  useInput((inputChar, key) => {
    if (key.escape) {
      exit();
    }
  });

  const slashCommands = useMemo(
    () =>
      createSlashCommands({
        onHelp: () => {
          const helpText = getHelpText(slashCommands);
          addMessage?.({ role: "system", content: helpText, timestamp: Date.now() });
        },
        onClear: () => {
          onClear?.();
        },
        onStatus: () => {
          const statusText = [
            `Connected: ${connected}`,
            `Session: ${session_id || "none"}`,
            `Model: ${model}`,
            `Tokens: ${tokens_used}/${tokens_max}`,
          ].join("\n");
          addMessage?.({ role: "system", content: statusText, timestamp: Date.now() });
        },
        onNewSession: (target?: string) => {
          onNewSession?.(target);
        },
        onQuit: () => {
          exit();
        },
      }),
    [connected, session_id, model, tokens_used, tokens_max, onClear, onNewSession, addMessage, exit]
  );

  const handleSubmit = (value: string) => {
    const trimmed = value.trim();
    if (!trimmed) return;

    // Handle slash commands
    const cmd = matchSlashCommand(trimmed, slashCommands);
    if (cmd) {
      cmd.handler();
      setInput("");
      return;
    }

    setHistory((prev) => [...prev, trimmed]);
    setHistoryIndex(-1);
    setInput("");
    onsubmit(trimmed);
  };

  return (
    <Box flexDirection="column" height="100%">
      {/* Header */}
      <Box borderStyle="single" borderColor={colors.border} paddingX={1}>
        <Text bold color={colors.primary}>
          ⚕ Fenrys-CAI
        </Text>
        <Text dimColor> v0.1.0</Text>
        {session_id && (
          <Text dimColor> │ {session_id}</Text>
        )}
        <Text dimColor> │ {theme}</Text>
      </Box>

      {/* Status Bar */}
      <StatusBar
        model={model}
        tokens_used={tokens_used}
        tokens_max={tokens_max}
        cost={cost}
        status={status}
        connected={connected}
      />

      {/* Main Content */}
      <Box flexDirection="column" flexGrow={1} paddingY={1}>
        <ChatPane messages={messages} />
        {tool_calls.length > 0 && <ToolTree tool_calls={tool_calls} />}
      </Box>

      {/* Input */}
      <Box borderStyle="single" borderColor={colors.border} paddingX={1}>
        <Text color={colors.primary} bold>
          ❯{" "}
        </Text>
        <TextInput
          value={input}
          onChange={setInput}
          onSubmit={handleSubmit}
          placeholder={connected ? "Ask Fenrys..." : "Connecting..."}
        />
      </Box>

      {/* Footer */}
      <Box>
        <Text dimColor>
          ESC: quit │ Tab: autocomplete │ Enter: send
        </Text>
      </Box>
    </Box>
  );
}
