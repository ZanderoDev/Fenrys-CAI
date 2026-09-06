import React from "react";
import { Box, Text } from "ink";

interface StatusBarProps {
  model: string;
  tokens_used: number;
  tokens_max: number;
  cost: number;
  status: string;
  connected: boolean;
}

function ContextBar({ used, max }: { used: number; max: number }): React.ReactElement {
  const pct = max > 0 ? (used / max) * 100 : 0;
  const filled = Math.round(pct / 10);
  const bar = "█".repeat(filled) + "░".repeat(10 - filled);
  return (
    <Text>
      [{bar}] {pct.toFixed(0)}%
    </Text>
  );
}

export function StatusBar({
  model,
  tokens_used,
  tokens_max,
  cost,
  status,
  connected,
}: StatusBarProps): React.ReactElement {
  const statusColor = !connected ? "red" : status === "ready" ? "green" : "yellow";
  const statusIcon = !connected ? "✗" : status === "ready" ? "●" : "○";

  return (
    <Box>
      <Text color={statusColor}>
        {statusIcon}{" "}
      </Text>
      <Text bold>{model}</Text>
      <Text> │ </Text>
      <Text>
        {tokens_used.toLocaleString()}/{tokens_max.toLocaleString()}
      </Text>
      <Text> </Text>
      <ContextBar used={tokens_used} max={tokens_max} />
      <Text> │ </Text>
      <Text color="cyan">${cost.toFixed(4)}</Text>
      {status !== "ready" && (
        <>
          <Text> │ </Text>
          <Text color="yellow">{status}</Text>
        </>
      )}
    </Box>
  );
}
