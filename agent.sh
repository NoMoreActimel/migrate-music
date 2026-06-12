#!/bin/bash
# Manage the background matching agent (macOS launchd LaunchAgent).
# Paths are derived from the repo location, so this works for any checkout.
#   ./agent.sh install [script]  - generate plist, load it, start now
#                                  (script defaults to auto_match.py; e.g. auto_recover.py)
#   ./agent.sh status            - loaded/running? recent log
#   ./agent.sh log               - follow the live log
#   ./agent.sh restart           - kick it (after editing code)
#   ./agent.sh uninstall         - stop and remove it
# Note: launchd is macOS-only. On Linux, run `python auto_match.py` under
# systemd/nohup instead — the supervisor logic is identical.
set -e

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$REPO/.venv/bin/python"; [ -x "$PY" ] || PY="$(command -v python3)"
LABEL="com.migrate-music.agent"
DEST="$HOME/Library/LaunchAgents/${LABEL}.plist"
DOMAIN="gui/$(id -u)"
LOG="$REPO/data/agent.log"
SCRIPT="${2:-auto_match.py}"

write_plist() {
  mkdir -p "$HOME/Library/LaunchAgents" "$REPO/data"
  cat > "$DEST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>${LABEL}</string>
  <key>ProgramArguments</key><array>
    <string>${PY}</string><string>${REPO}/${SCRIPT}</string>
  </array>
  <key>WorkingDirectory</key><string>${REPO}</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
  <key>ProcessType</key><string>Background</string>
  <key>StandardOutPath</key><string>${LOG}</string>
  <key>StandardErrorPath</key><string>${LOG}</string>
</dict></plist>
EOF
}

case "${1:-}" in
  install)
    write_plist
    launchctl bootout  "$DOMAIN" "$DEST" 2>/dev/null || true
    launchctl bootstrap "$DOMAIN" "$DEST"
    launchctl enable "${DOMAIN}/${LABEL}" 2>/dev/null || true
    echo "Installed ($SCRIPT). Survives terminal close & reboot (starts at login)."
    echo "Watch: ./agent.sh log"
    ;;
  status)
    launchctl print "${DOMAIN}/${LABEL}" 2>/dev/null | grep -E "state =|pid =|last exit" || echo "not loaded."
    echo "--- last 15 log lines ---"; tail -n 15 "$LOG" 2>/dev/null | tr '\r' '\n' || echo "(no log yet)"
    ;;
  log) tail -f "$LOG" | tr '\r' '\n' ;;
  restart) launchctl kickstart -k "${DOMAIN}/${LABEL}"; echo "restarted." ;;
  uninstall)
    launchctl bootout "$DOMAIN" "$DEST" 2>/dev/null || true
    rm -f "$DEST"; echo "stopped and removed." ;;
  *) echo "usage: ./agent.sh {install [script]|status|log|restart|uninstall}"; exit 1 ;;
esac
