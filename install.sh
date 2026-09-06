#!/usr/bin/env bash
set -euo pipefail

# Fenrys-CAI Installer
# Installs Python backend + Node.js TUI

BOLD="\033[1m"
GREEN="\033[32m"
YELLOW="\033[33m"
RED="\033[31m"
RESET="\033[0m"

info()  { echo -e "${BOLD}$1${RESET}"; }
ok()    { echo -e "${GREEN}✓${RESET} $1"; }
warn()  { echo -e "${YELLOW}⚠${RESET} $1"; }
fail()  { echo -e "${RED}✗${RESET} $1"; exit 1; }

# ─── Prerequisites ──────────────────────────────────────────────────────────

info "Checking prerequisites..."

# Python 3.13+
if command -v python3 &>/dev/null; then
    PY_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
    ok "Python $PY_VERSION"
else
    fail "Python 3.13+ required. Install: https://python.org"
fi

# uv (Python package manager)
if command -v uv &>/dev/null; then
    ok "uv $(uv --version 2>/dev/null | head -1)"
else
    warn "uv not found. Installing..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    ok "uv installed"
fi

# Node.js 18+
if command -v node &>/dev/null; then
    ok "Node.js $(node --version)"
else
    warn "Node.js not found. Installing via nvm..."
    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.0/install.sh | bash
    export NVM_DIR="$HOME/.nvm"
    [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
    nvm install 20
    ok "Node.js installed"
fi

# npm
if command -v npm &>/dev/null; then
    ok "npm $(npm --version)"
else
    fail "npm not found"
fi

# ─── Install Fenrys-CAI ─────────────────────────────────────────────────────

info "Installing Fenrys-CAI..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Install Python dependencies
info "Installing Python dependencies..."
cd "$SCRIPT_DIR"
uv sync
ok "Python dependencies installed"

# Build Python package
info "Building Python package..."
uv build
ok "Python package built"

# Install Node.js TUI
info "Installing Node.js TUI..."
cd "$SCRIPT_DIR/ui"
npm install
npm run build
ok "Node.js TUI built"

# ─── Configuration ──────────────────────────────────────────────────────────

info "Setting up configuration..."

# Create config directory
mkdir -p ~/.config/fenrys-cai

# Copy default configs if not present
if [ ! -f ~/.config/fenrys-cai/config.yaml ]; then
    cp "$SCRIPT_DIR/config/defaults/config.yaml" ~/.config/fenrys-cai/
    ok "Default config created"
else
    ok "Config already exists"
fi

if [ ! -f ~/.config/fenrys-cai/scope.yaml ]; then
    cp "$SCRIPT_DIR/config/defaults/scope.yaml" ~/.config/fenrys-cai/
fi

if [ ! -f ~/.config/fenrys-cai/policy.yaml ]; then
    cp "$SCRIPT_DIR/config/defaults/policy.yaml" ~/.config/fenrys-cai/
fi

# ─── Verify ─────────────────────────────────────────────────────────────────

info "Verifying installation..."

cd "$SCRIPT_DIR"

# Check Python
if uv run python -c "import fenrys" 2>/dev/null; then
    ok "Python package importable"
else
    warn "Python import check failed"
fi

# Check Node.js
cd "$SCRIPT_DIR/ui"
if npx tsc --noEmit 2>/dev/null; then
    ok "TypeScript compiles"
else
    warn "TypeScript check failed"
fi

# ─── Done ───────────────────────────────────────────────────────────────────

echo ""
info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
ok "Installation complete!"
info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  Start Fenrys-CAI:"
echo "    cd $SCRIPT_DIR"
echo "    fenrys                  # Launch TUI"
echo "    fenrys gateway          # Start gateway server"
echo "    cd ui && npm run dev    # Launch Node.js TUI"
echo ""
echo "  Or use the shortcut:"
echo "    fenrys scan             # Quick scan mode"
echo ""
echo "  Configure:"
echo "    fenrys setup            # Run setup wizard"
echo "    fenrys doctor           # Check system health"
echo ""
