from __future__ import annotations

from textual.widget import Widget
from textual.widgets import Static


class StatusBar(Widget):
    """Live status bar: model, tokens, context usage, cost."""

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        dock: bottom;
        padding: 0 1;
        background: $accent-darken-2;
        color: $text;
    }
    #status-text {
        width: 100%;
    }
    """

    def compose(self):
        yield Static(self._render(), id="status-text")

    def __init__(self, model: str = "", **kwargs):
        super().__init__(**kwargs)
        self.model = model
        self.tokens_used = 0
        self.tokens_max = 128_000
        self.cost = 0.0
        self._status = "ready"

    def _render(self) -> str:
        pct = (self.tokens_used / self.tokens_max * 100) if self.tokens_max else 0
        filled = int(pct / 10)
        bar = "\u2588" * filled + "\u2591" * (10 - filled)
        model_display = self.model[:26] if self.model else "no model"
        return (
            f"\u2695 {model_display} \u2502 "
            f"{self.tokens_used:,}/{self.tokens_max:,} \u2502 "
            f"[{bar}] {pct:.0f}% \u2502 "
            f"${self.cost:.2f} \u2502 "
            f"{self._status}"
        )

    def set_status(self, status: str):
        self._status = status
        self._refresh()

    def set_model(self, model: str):
        self.model = model
        self._refresh()

    def update_tokens(self, used: int, max_tokens: int | None = None):
        self.tokens_used = used
        if max_tokens:
            self.tokens_max = max_tokens
        self._refresh()

    def update_cost(self, cost: float):
        self.cost = cost
        self._refresh()

    def _refresh(self):
        try:
            self.query_one("#status-text", Static).update(self._render())
        except Exception:
            pass
