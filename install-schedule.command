#!/bin/zsh
# Install (or reinstall) a daily background run of Unsubscribe via launchd.
# Double-click to enable the schedule. Runs once a day at 09:00.
set -e
cd "$(dirname "$0")"

REPO="$(pwd)"
PY="$(command -v python3 || true)"
LABEL="com.local.unsubscribe"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
STATE="$HOME/Library/Application Support/Unsubscribe"

if [[ -z "$PY" ]]; then
  echo "python3 not found. Run 'xcode-select --install' once, then try again."
  echo "Press any key to close..."; read -k1; exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents" "$STATE"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>            <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PY</string>
    <string>$REPO/unsubscribe.py</string>
  </array>
  <key>WorkingDirectory</key> <string>$REPO</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>    <integer>9</integer>
    <key>Minute</key> <integer>0</integer>
  </dict>
  <key>StandardOutPath</key>  <string>$STATE/launchd.log</string>
  <key>StandardErrorPath</key><string>$STATE/launchd.log</string>
</dict>
</plist>
EOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "Scheduled: Unsubscribe will run daily at 09:00."
echo "Plist: $PLIST"
echo ""
echo "To disable later:  launchctl unload \"$PLIST\" && rm \"$PLIST\""
echo ""
echo "Press any key to close..."; read -k1
