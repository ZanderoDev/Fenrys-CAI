import React from "react";
import { Box, Text } from "ink";
import type { ChatMessage } from "../types.js";

interface ChatPaneProps {
  messages: ChatMessage[];
  maxHeight?: number;
}

function UserMessage({ content }: { content: string }): React.ReactElement {
  return (
    <Box flexDirection="column" marginBottom={1}>
      <Text color="blue" bold>
        ❯{" "}
      </Text>
      <Text>{content}</Text>
    </Box>
  );
}

function AssistantMessage({ content }: { content: string }): React.ReactElement {
  return (
    <Box flexDirection="column" marginBottom={1}>
      <Text color="green" bold>
        ◆{" "}
      </Text>
      <Text>{content}</Text>
    </Box>
  );
}

function SystemMessage({ content }: { content: string }): React.ReactElement {
  return (
    <Box marginBottom={1}>
      <Text color="yellow" dimColor>
        ⚠ {content}
      </Text>
    </Box>
  );
}

export function ChatPane({ messages, maxHeight = 50 }: ChatPaneProps): React.ReactElement {
  const visibleMessages = messages.slice(-maxHeight);

  return (
    <Box flexDirection="column">
      {visibleMessages.length === 0 ? (
        <Text dimColor>
          Type a message to start. Use /help for commands.
        </Text>
      ) : (
        visibleMessages.map((msg, i) => {
          switch (msg.role) {
            case "user":
              return <UserMessage key={i} content={msg.content} />;
            case "assistant":
              return <AssistantMessage key={i} content={msg.content} />;
            case "system":
            case "tool":
              return <SystemMessage key={i} content={msg.content} />;
            default:
              return null;
          }
        })
      )}
    </Box>
  );
}
