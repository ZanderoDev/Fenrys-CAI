NIGHTSHADE_COLORS = {
    "background": "#120B22",
    "surface": "#1E1333",
    "surface_alt": "#2A1B47",
    "border": "#6D28D9",
    "border_dim": "#4C1D95",
    "primary": "#8B5CF6",
    "primary_bright": "#A78BFA",
    "accent": "#C4B5FD",
    "text": "#EDE9FE",
    "text_muted": "#9CA3AF",
    "success": "#22C55E",
    "warning": "#F59E0B",
    "danger": "#EF4444",
    "info": "#60A5FA",
}

NIGHTSHADE_CSS = """
Screen { background: #120B22; color: #EDE9FE; }
Header { background: #1E1333; color: #A78BFA; }
Footer { background: #1E1333; color: #C4B5FD; }
.panel { background: #1E1333; border: round #6D28D9; padding: 1 2; margin: 1; }
.title { color: #A78BFA; text-style: bold; }
.muted { color: #9CA3AF; }
.ok { color: #22C55E; }
.warning { color: #F59E0B; }
.danger { color: #EF4444; }
Button { background: #2A1B47; color: #EDE9FE; border: round #6D28D9; }
Button.-active { background: #8B5CF6; color: #120B22; }
Input, Select { background: #2A1B47; border: round #4C1D95; }
Input#command { margin: 0 1; border: round #6D28D9; }
Static#command-output { height: 2; margin: 0 1; color: #C4B5FD; }
DataTable { background: #1E1333; }
"""
