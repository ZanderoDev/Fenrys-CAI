#!/usr/bin/env bash
set -euo pipefail

# Fenrys Gateway Integration Test

PASS=0
FAIL=0

green() { echo -e "\033[32m$1\033[0m"; }
red()   { echo -e "\033[31m$1\033[0m"; }
bold()  { echo -e "\033[1m$1\033[0m"; }

assert_contains() {
    local result="$1" expected="$2" test_name="$3"
    if echo "$result" | grep -q "$expected"; then
        green "  ✓ $test_name"
        PASS=$((PASS + 1))
    else
        red "  ✗ $test_name"
        FAIL=$((FAIL + 1))
    fi
}

gateway_request() {
    echo "$1" | timeout 10 uv run python -m fenrys.gateway 2>/dev/null | head -1
}

# ─── Test 1: Ping ───────────────────────────────────────────────────────────

bold "Test 1: Ping"
RESULT=$(gateway_request '{"jsonrpc":"2.0","id":1,"method":"ping","params":{}}')
assert_contains "$RESULT" "pong" "Returns pong"

# ─── Test 2: Health ─────────────────────────────────────────────────────────

bold "Test 2: Health"
RESULT=$(gateway_request '{"jsonrpc":"2.0","id":2,"method":"health","params":{}}')
assert_contains "$RESULT" "fenrys" "Has fenrys field"
assert_contains "$RESULT" "hexstrike" "Has hexstrike field"
assert_contains "$RESULT" "71/127" "Tools count"

# ─── Test 3: Session Create ─────────────────────────────────────────────────

bold "Test 3: Session Create"
RESULT=$(gateway_request '{"jsonrpc":"2.0","id":3,"method":"session.new","params":{"target":"10.10.10.1","mode":"CTF"}}')
assert_contains "$RESULT" "session_id" "Has session_id"
SESSION_ID=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['session_id'])" 2>/dev/null || echo "")

# ─── Test 4: Session List ───────────────────────────────────────────────────

bold "Test 4: Session List"
RESULT=$(gateway_request '{"jsonrpc":"2.0","id":4,"method":"session.list","params":{}}')
assert_contains "$RESULT" "sessions" "Has sessions"

# ─── Test 5: Session Get ────────────────────────────────────────────────────

bold "Test 5: Session Get"
if [ -n "$SESSION_ID" ]; then
    RESULT=$(gateway_request "{\"jsonrpc\":\"2.0\",\"id\":5,\"method\":\"session.get\",\"params\":{\"session_id\":\"$SESSION_ID\"}}")
    assert_contains "$RESULT" "session" "Has session"
else
    red "  ✗ Skipped (no session_id)"
    FAIL=$((FAIL + 1))
fi

# ─── Test 6: Unknown Method ─────────────────────────────────────────────────

bold "Test 6: Unknown Method"
RESULT=$(gateway_request '{"jsonrpc":"2.0","id":6,"method":"nonexistent","params":{}}')
assert_contains "$RESULT" "Method not found" "Error message"

# ─── Test 7: Invalid JSON ──────────────────────────────────────────────────

bold "Test 7: Invalid JSON"
RESULT=$(echo "not json" | timeout 5 uv run python -m fenrys.gateway 2>/dev/null | head -1)
assert_contains "$RESULT" "Parse error" "Parse error"

# ─── Test 8: Session Delete ─────────────────────────────────────────────────

bold "Test 8: Session Delete"
if [ -n "$SESSION_ID" ]; then
    RESULT=$(gateway_request "{\"jsonrpc\":\"2.0\",\"id\":8,\"method\":\"session.delete\",\"params\":{\"session_id\":\"$SESSION_ID\"}}")
    assert_contains "$RESULT" "deleted" "Session deleted"
else
    red "  ✗ Skipped (no session_id)"
    FAIL=$((FAIL + 1))
fi

# ─── Test 9: Prompt (streaming) ─────────────────────────────────────────────

bold "Test 9: Prompt (streaming events)"
RESULT=$(printf '{"jsonrpc":"2.0","id":1,"method":"session.new","params":{"target":"10.10.10.1","mode":"CTF"}}\n{"jsonrpc":"2.0","id":2,"method":"prompt","params":{"text":"hello"}}\n' | timeout 20 uv run python -m fenrys.gateway 2>/dev/null)
# Prompt may fail without API key - that's OK, gateway still works
if echo "$RESULT" | grep -q "error.*API key"; then
    green "  ✓ Prompt handled gracefully (no API key configured)"
    PASS=$((PASS + 1))
else
    assert_contains "$RESULT" "token" "Token events emitted"
    assert_contains "$RESULT" "response.done" "Response done event"
fi

# ─── Summary ────────────────────────────────────────────────────────────────

echo ""
bold "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ $FAIL -eq 0 ]; then
    green "ALL TESTS PASSED ($PASS/$((PASS + FAIL)))"
else
    red "FAILED: $FAIL / $((PASS + FAIL))"
fi
bold "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

exit $FAIL
