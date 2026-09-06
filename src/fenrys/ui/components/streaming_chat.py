from __future__ import annotations

from textual.widget import Widget
from textual.widgets import RichLog


class StreamingChat(Widget):
    """Chat pane with streaming token support."""

    DEFAULT_CSS = """
    StreamingChat {
        height: 1fr;
    }
    #chat {
        height: 100%;
    }
    """

    def compose(self):
        yield RichLog(id="chat", highlight=True, markup=True, wrap=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._buffer = ""
        self._log_widget: RichLog | None = None

    def _get_log(self) -> RichLog:
        if self._log_widget is None:
            self._log_widget = self.query_one("#chat", RichLog)
        return self._log_widget

    def write_message(self, text: str, **kwargs):
        """Write a complete message to the chat."""
        self._get_log().write(text, **kwargs)

    def write_user(self, text: str):
        """Write a user message."""
        self._get_log().write(f"[bold cyan]\u25b8[/bold cyan] {text}")

    def write_token(self, delta: str):
        """Append a streaming token to the current response buffer."""
        self._buffer += delta

    def flush_tokens(self, prefix: str = "[bold]Fenrys[/bold] "):
        """Flush the token buffer to the log as a complete message."""
        if self._buffer:
            self._get_log().write(prefix + self._buffer)
            self._buffer = ""

    def write_tool_event(self, kind: str, payload: str):
        """Write a tool execution event."""
        if kind == "tool":
            self._get_log().write(f"[cyan]\u2699 {payload}[/cyan]")
        elif kind == "result":
            self._get_log().write(f"[green]\u2713 {payload}[/green]")
        elif kind == "delegate":
            self._get_log().write(f"[magenta]\u2514 {payload}[/magenta]")
        elif kind == "error":
            self._get_log().write(f"[red]! {payload}[/red]")

    def clear(self):
        """Clear the chat log."""
        self._get_log().clear()
        self._buffer = ""
