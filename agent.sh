#!/bin/bash
# Manage the background matching agent (macOS launchd LaunchAgent).
#   ./agent.sh install   - copy plist, load it, start matching now
#   ./agent.sh status    - is it loaded/running? show recent log
#   ./agent.sh log       - follow the live log
#   ./agent.sh restart   - kick it (e.g. after editing code)
#   ./agent.sh uninstall - stop and remove it
set -e

LABEL="com.evolu.migrate-music"
SRC="/Users/evolu/research/migrate-music/${LABEL}.plist"
DEST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
DOMAIN="gui/$(id -u)"
LOG="/Users/evolu/research/migrate-music/data/agent.log"

case "${1:-}" in
  install)
    mkdir -p "${HOME}/Library/LaunchAgents"
    cp "$SRC" "$DEST"
    launchctl bootout  "$DOMAIN" "$DEST" 2>/dev/null || true
    launchctl bootstrap "$DOMAIN" "$DEST"
    launchctl enable "${DOMAIN}/${LABEL}" 2>/dev/null || true
    echo "Installed and started. Survives terminal close & reboot (starts at login)."
    echo "Watch progress: ./agent.sh log"
    ;;
  status)
    if launchctl print "${DOMAIN}/${LABEL}" >/dev/null 2>&1; then
      echo "loaded. state:"
      launchctl print "${DOMAIN}/${LABEL}" | grep -E "state =|pid =|last exit" || true
    else
      echo "not loaded."
    fi
    echo "--- last 15 log lines ---"; tail -n 15 "$LOG" 2>/dev/null | tr '\r' '\n' || echo "(no log yet)"
    ;;
  log)
    tail -f "$LOG" | tr '\r' '\n'
    ;;
  restart)
    launchctl kickstart -k "${DOMAIN}/${LABEL}"
    echo "restarted."
    ;;
  uninstall)
    launchctl bootout "$DOMAIN" "$DEST" 2>/dev/null || true
    rm -f "$DEST"
    echo "stopped and removed."
    ;;
  *)
    echo "usage: ./agent.sh {install|status|log|restart|uninstall}"; exit 1 ;;
esac
