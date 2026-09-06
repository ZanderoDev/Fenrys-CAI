from __future__ import annotations

from textual.widget import Widget
from textual.widgets import Static


class ToolTree(Widget):
    """Visual tool execution tree with status and duration."""

    DEFAULT_CSS = """
    ToolTree {
        height: auto;
        max-height: 8;
        padding: 0 1;
        border-top: solid $accent;
    }
    #tool-list {
        width: 100%;
    }
    """

    def compose(self):
        yield Static("", id="tool-list")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._tools: list[dict] = []

    def add_tool(self, name: str, target: str = ""):
        """Add a tool that's starting execution."""
        self._tools.append({
            "name": name,
            "target": target,
            "success": None,
            "duration_ms": 0,
            "findings": [],
        })
        self._refresh()

    def finish_tool(self, name: str, success: bool, duration_ms: int = 0, summary: str = ""):
        """Mark a tool as finished."""
        for tool in reversed(self._tools):
            if tool["name"] == name and tool["success"] is None:
                tool["success"] = success
                tool["duration_ms"] = duration_ms
                break
        self._refresh()

    def add_finding(self, name: str, finding: str):
        """Add a finding to a tool's output."""
        for tool in reversed(self._tools):
            if tool["name"] == name:
                tool["findings"].append(finding)
                break
        self._refresh()

    def clear(self):
        """Clear all tool entries."""
        self._tools.clear()
        self._refresh()

    def _refresh(self):
        lines = []
        for tool in self._tools:
            if tool["success"] is None:
                status = "[cyan]\u23f3[/cyan]"  # hourglass
            elif tool["success"]:
                status = "[green]\u2713[/green]"  # checkmark
            else:
                status = "[red]\u2717[/red]"  # cross

            duration = f"{tool['duration_ms']}ms" if tool["duration_ms"] else ""
            target = f" {tool['target']}" if tool["target"] else ""
            lines.append(f"  {status} {tool['name']}{target} {duration}")

            for finding in tool.get("findings", []):
                lines.append(f"    \u2514\u2500 {finding}")

        text = "\n".join(lines) if lines else ""
        try:
            self.query_one("#tool-list", Static).update(text)
        except Exception:
            pass
