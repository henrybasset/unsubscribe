#!/bin/zsh
# Build Unsubscribe.app from unsubscribe.py and install it to /Applications
# (falls back to ~/Applications if /Applications isn't writable).
# Double-click this, or run it from a terminal.
set -e
cd "${0:A:h}"          # repo dir (this script's folder)
REPO="$(pwd)"

# Pick a python3 to bake into the app (GUI apps have a minimal PATH).
PY="$(command -v python3 || true)"
[[ -z "$PY" ]] && PY="/usr/bin/python3"

APPNAME="Unsubscribe"
DEST="/Applications"
[[ -w "$DEST" ]] || DEST="$HOME/Applications"
mkdir -p "$DEST"
APP="$DEST/$APPNAME.app"

echo "Building $APP ..."
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

# The actual program logic, bundled so the app is self-contained.
cp "$REPO/unsubscribe.py" "$APP/Contents/Resources/unsubscribe.py"

# Info.plist
cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>              <string>Unsubscribe</string>
  <key>CFBundleDisplayName</key>       <string>Unsubscribe</string>
  <key>CFBundleIdentifier</key>        <string>com.henrybasset.unsubscribe</string>
  <key>CFBundleVersion</key>           <string>1.0</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundlePackageType</key>       <string>APPL</string>
  <key>CFBundleExecutable</key>        <string>Unsubscribe</string>
  <key>CFBundleIconFile</key>          <string>Unsubscribe</string>
  <key>LSMinimumSystemVersion</key>    <string>10.13</string>
  <key>NSHumanReadableCopyright</key>  <string>MIT License</string>
</dict>
</plist>
PLIST

# Launcher executable (quoted heredoc = no shell expansion; __PY__ filled below).
cat > "$APP/Contents/MacOS/$APPNAME" <<'WRAP'
#!/bin/zsh
DIR="${0:A:h}"
SCRIPT="$DIR/../Resources/unsubscribe.py"
PY=""
for c in __PY__ /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
  if [[ -x "$c" ]]; then PY="$c"; break; fi
done
[[ -z "$PY" ]] && PY="$(command -v python3 2>/dev/null)"
if [[ -z "$PY" ]]; then
  osascript -e 'display dialog "python3 not found. Open Terminal and run: xcode-select --install" with title "Unsubscribe" buttons {"OK"}'
  exit 1
fi
exec "$PY" "$SCRIPT" --notify "$@"
WRAP

# Bake in the python path discovered at build time.
/usr/bin/sed -i '' "s#__PY__#$PY#" "$APP/Contents/MacOS/$APPNAME"
chmod +x "$APP/Contents/MacOS/$APPNAME"

# App icon: build Unsubscribe.icns from Unsubscribe.png (regenerate it if the
# generator is present but the PNG is missing).
if [[ ! -f "$REPO/Unsubscribe.png" && -f "$REPO/generate_icon.py" ]]; then
  "$PY" "$REPO/generate_icon.py" || true
fi
if [[ -f "$REPO/Unsubscribe.png" ]]; then
  ICONSET="$(mktemp -d)/Unsubscribe.iconset"
  mkdir -p "$ICONSET"
  for sz in 16 32 128 256 512; do
    sips -z $sz $sz       "$REPO/Unsubscribe.png" --out "$ICONSET/icon_${sz}x${sz}.png"     >/dev/null
    sips -z $((sz*2)) $((sz*2)) "$REPO/Unsubscribe.png" --out "$ICONSET/icon_${sz}x${sz}@2x.png" >/dev/null
  done
  iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/Unsubscribe.icns"
  rm -rf "$ICONSET"
fi

# Ad-hoc code signature gives the app a stable identity, so the macOS
# "allow control of Mail" permission keeps sticking across rebuilds.
codesign --force --deep --sign - "$APP" 2>/dev/null || true

echo "Installed: $APP"
echo "Open it from Finder (Applications) or Spotlight: 'Unsubscribe'."
if [[ "$1" != "--quiet" ]]; then
  echo ""
  echo "Press any key to close..."; read -k1
fi
