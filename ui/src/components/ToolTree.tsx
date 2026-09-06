import React from "react";
import { Box, Text } from "ink";
import type { ToolCall } from "../types.js";

interface ToolTreeProps {
  tool_calls: ToolCall[];
  maxVisible?: number;
}

function ToolItem({ tool }: { tool: ToolCall }): React.ReactElement {
  const icon =
    tool.status === "running" ? (
      <Text color="yellow">⟳</Text>
    ) : tool.status === "ok" ? (
      <Text color="green">✓</Text>
    ) : (
      <Text color="red">✗</Text>
    );

  const duration = tool.duration_ms ? <Text dimColor> {tool.duration_ms}ms</Text> : null;

  const target = tool.target ? <Text dimColor> → {tool.target}</Text> : null;

  return (
    <Box>
      <Text>  </Text>
      {icon}
      <Text> {tool.name}</Text>
      {target}
      {duration}
    </Box>
  );
}

export function ToolTree({ tool_calls, maxVisible = 10 }: ToolTreeProps): React.ReactElement {
  const visible = tool_calls.slice(-maxVisible);
  const running = visible.filter((t) => t.status === "running").length;

  if (visible.length === 0) {
    return <Box />;
  }

  return (
    <Box flexDirection="column" borderStyle="round" borderColor="gray" paddingX={1}>
      <Text bold color="cyan">
        Tools {running > 0 ? `(${running} running)` : ""}
      </Text>
      {visible.map((tool, i) => (
        <ToolItem key={i} tool={tool} />
      ))}
    </Box>
  );
}
