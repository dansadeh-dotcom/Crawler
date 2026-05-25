#!/usr/bin/env bash
# run_with_vpn.sh
# Connects to a US ExpressVPN server, runs the crawler, then disconnects.
# Used by the launchd job (com.crawler.daily.plist) for autonomous daily runs.

set -euo pipefail

EXPRESSVPN="/usr/local/bin/expressvpnctl"
US_SERVER="${CRAWLER_VPN_SERVER:-usa-atlanta}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$PROJECT_DIR/venv/bin/python"
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)]  Starting VPN-wrapped crawler run"

# ── 1. Connect to US VPN ──────────────────────────────────────────────────────
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)]  Connecting to ExpressVPN ($US_SERVER)…"
_TIMEOUT_CMD=""
if command -v timeout &>/dev/null; then
    _TIMEOUT_CMD="timeout 30"
elif command -v gtimeout &>/dev/null; then
    _TIMEOUT_CMD="gtimeout 30"
fi
if ! $_TIMEOUT_CMD "$EXPRESSVPN" connect "$US_SERVER"; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)]  ERROR: VPN connect timed out or failed. Aborting."
    exit 1
fi

# Give the VPN tunnel a moment to fully establish
sleep 5

# ── 2. Verify we are on a US IP ───────────────────────────────────────────────
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)]  Verifying egress IP…"
# api.country.is returns {"ip":"...","country":"XX"} and is reliable without rate limits.
# Fall back to ipinfo.io if that also fails.
_RAW=$(curl -sf --max-time 10 "https://api.country.is/" 2>/dev/null || true)
DETECTED_COUNTRY=$(echo "$_RAW" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('country','UNKNOWN'))" 2>/dev/null || true)
if [[ -z "$DETECTED_COUNTRY" ]]; then
    DETECTED_COUNTRY=$(curl -sf --max-time 10 "https://ipinfo.io/country" 2>/dev/null | tr -d '[:space:]' || echo "UNKNOWN")
fi
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)]  Egress country: $DETECTED_COUNTRY"

if [[ "$DETECTED_COUNTRY" != "US" ]]; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)]  ERROR: Expected US egress but got '$DETECTED_COUNTRY'. Aborting crawl."
    "$EXPRESSVPN" disconnect || true
    exit 1
fi

# ── 3. Run the crawler ────────────────────────────────────────────────────────
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)]  Running crawler…"
cd "$PROJECT_DIR"
"$PYTHON" run.py
CRAWLER_EXIT=$?

# ── 4. Disconnect VPN ─────────────────────────────────────────────────────────
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)]  Disconnecting VPN…"
"$EXPRESSVPN" disconnect || true

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)]  Done (crawler exit code: $CRAWLER_EXIT)"
exit $CRAWLER_EXIT
