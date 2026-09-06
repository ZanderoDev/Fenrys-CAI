import React, { useCallback } from "react";
import { AppLayout } from "./components/AppLayout.js";
import { useGateway } from "./hooks/useGateway.js";
import type { ChatMessage } from "./types.js";

export default function App(): React.ReactElement {
  const gateway = useGateway();

  const addMessage = useCallback((msg: ChatMessage) => {
    // This is a workaround since useGateway doesn't expose addMessage
    // In a real app, you'd lift this state up
    console.log("System message:", msg.content);
  }, []);

  return (
    <AppLayout
      connected={gateway.connected}
      session_id={gateway.session_id}
      messages={gateway.messages}
      tool_calls={gateway.tool_calls}
      status={gateway.status}
      model={gateway.model}
      tokens_used={gateway.tokens_used}
      tokens_max={gateway.tokens_max}
      cost={gateway.cost}
      onsubmit={gateway.sendPrompt}
      onClear={gateway.clearMessages}
      onNewSession={gateway.newSession}
      addMessage={addMessage}
    />
  );
}
