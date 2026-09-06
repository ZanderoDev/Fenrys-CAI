NIGHTSHADE_COLORS = {
    "background": "#09090b",
    "foreground": "#e4e4e7",
    "muted": "#71717a",
    "panel": "#111113",
    "border": "#18181b",
    "accent": "#a78bfa",
    "accent_focus": "#7c3aed",
    "scrollbar": "#27272a",
}

NIGHTSHADE_CSS = """
Screen { background: #09090b; color: #e4e4e7; }
Footer { background: #09090b; color: #71717a; border-top: solid #18181b; }
#brand { height: 1; padding: 0 1; color: #a78bfa; text-style: bold; }
#topbar { height: 1; padding: 0 1; color: #71717a; border-bottom: solid #18181b; }
#chat { height: 1fr; padding: 1 2; background: #09090b; scrollbar-color: #27272a; scrollbar-background: #09090b; }
#status { height: 1; padding: 0 2; color: #a1a1aa; }
#input-wrap { height: 5; margin: 0 1; border: solid #27272a; background: #111113; }
#input-wrap:focus-within { border: solid #7c3aed; }
FenrysInput { background: #111113; color: #fafafa; height: 1fr; border: none; padding: 0 1; }
FenrysInput:focus { border: none; }
#hints { height: 1; padding: 0 1; color: #52525b; }
"""
