export interface SlashCommand {
  name: string;
  description: string;
  aliases?: string[];
  handler: () => void | Promise<void>;
}

export function createSlashCommands(handlers: {
  onHelp: () => void;
  onClear: () => void;
  onStatus: () => void;
  onNewSession: (target?: string) => void;
  onQuit: () => void;
}): SlashCommand[] {
  return [
    {
      name: "/help",
      description: "Show available commands",
      aliases: ["/h", "/?"],
      handler: handlers.onHelp,
    },
    {
      name: "/clear",
      description: "Clear chat history",
      aliases: ["/cls"],
      handler: handlers.onClear,
    },
    {
      name: "/status",
      description: "Show connection and session status",
      aliases: [],
      handler: handlers.onStatus,
    },
    {
      name: "/new",
      description: "Create a new session",
      aliases: ["/session"],
      handler: () => handlers.onNewSession(),
    },
    {
      name: "/quit",
      description: "Exit Fenrys",
      aliases: ["/exit", "/q"],
      handler: handlers.onQuit,
    },
  ];
}

export function matchSlashCommand(
  input: string,
  commands: SlashCommand[]
): SlashCommand | null {
  const trimmed = input.trim().toLowerCase();
  const parts = trimmed.split(/\s+/);
  const cmd = parts[0];

  for (const command of commands) {
    if (cmd === command.name || command.aliases?.includes(cmd)) {
      return command;
    }
  }
  return null;
}

export function getHelpText(commands: SlashCommand[]): string {
  const lines = ["Available commands:"];
  for (const cmd of commands) {
    const aliases = cmd.aliases?.length ? ` (${cmd.aliases.join(", ")})` : "";
    lines.push(`  ${cmd.name}${aliases} - ${cmd.description}`);
  }
  return lines.join("\n");
}
