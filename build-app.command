#!/bin/zsh
# Build Unsubscribe.app and install it to /Applications (falls back to
# ~/Applications if that isn't writable). Double-click, or run from a terminal.
#
# If swiftc is available it builds the native menu-bar app (Unsubscribe.swift);
# otherwise it falls back to a simple shell launcher that runs once and quits.
set -e
cd "${0:A:h}"          # repo dir (this script's folder)
REPO="$(pwd)"

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

# The program logic, bundled so the app is self-contained.
cp "$REPO/unsubscribe.py" "$APP/Contents/Resources/unsubscribe.py"
for extra in triage.py gmail_unsubscribe.py; do
  [[ -f "$REPO/$extra" ]] && cp "$REPO/$extra" "$APP/Contents/Resources/$extra"
done

# Info.plist — LSUIElement=true makes it a menu-bar agent (no Dock icon).
cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>              <string>Unsubscribe!</string>
  <key>CFBundleDisplayName</key>       <string>Unsubscribe!</string>
  <key>CFBundleIdentifier</key>        <string>com.henrybasset.unsubscribe</string>
  <key>CFBundleVersion</key>           <string>1.1</string>
  <key>CFBundleShortVersionString</key><string>1.1</string>
  <key>CFBundlePackageType</key>       <string>APPL</string>
  <key>CFBundleExecutable</key>        <string>Unsubscribe</string>
  <key>CFBundleIconFile</key>          <string>Unsubscribe</string>
  <key>LSMinimumSystemVersion</key>    <string>13.0</string>
  <key>LSUIElement</key>               <true/>
  <key>NSHumanReadableCopyright</key>  <string>MIT License</string>
</dict>
</plist>
PLIST

BUILT_NATIVE=0
if command -v swiftc >/dev/null 2>&1 && [[ -f "$REPO/Unsubscribe.swift" ]]; then
  echo "Compiling native menu-bar app with swiftc ..."
  TMP="$(mktemp -d)/Unsubscribe.swift"
  /usr/bin/sed "s#__PY__#$PY#" "$REPO/Unsubscribe.swift" > "$TMP"
  if swiftc -O "$TMP" -o "$APP/Contents/MacOS/$APPNAME" \
       -framework Cocoa -framework ServiceManagement 2>/tmp/unsub_swift_build.log; then
    BUILT_NATIVE=1
  else
    echo "swiftc failed; see /tmp/unsub_swift_build.log — falling back to shell launcher."
  fi
fi

if [[ "$BUILT_NATIVE" -eq 0 ]]; then
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
  /usr/bin/sed -i '' "s#__PY__#$PY#" "$APP/Contents/MacOS/$APPNAME"
fi
chmod +x "$APP/Contents/MacOS/$APPNAME"

# App icon: build Unsubscribe.icns from Unsubscribe.png (regenerate if needed).
if [[ ! -f "$REPO/Unsubscribe.png" && -f "$REPO/generate_icon.py" ]]; then
  "$PY" "$REPO/generate_icon.py" || true
fi
if [[ -f "$REPO/Unsubscribe.png" ]]; then
  ICONSET="$(mktemp -d)/Unsubscribe.iconset"
  mkdir -p "$ICONSET"
  for sz in 16 32 128 256 512; do
    sips -z $sz $sz             "$REPO/Unsubscribe.png" --out "$ICONSET/icon_${sz}x${sz}.png"     >/dev/null
    sips -z $((sz*2)) $((sz*2)) "$REPO/Unsubscribe.png" --out "$ICONSET/icon_${sz}x${sz}@2x.png" >/dev/null
  done
  iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/Unsubscribe.icns"
  rm -rf "$ICONSET"
fi

# Ad-hoc signature for a stable identity (Automation permission, login item).
codesign --force --deep --sign - "$APP" 2>/dev/null || true

MODE=$([[ "$BUILT_NATIVE" -eq 1 ]] && echo "native menu-bar app" || echo "shell launcher")
echo "Installed: $APP  ($MODE)"
echo "Open it from Finder/Spotlight ('Unsubscribe'). It appears in the menu bar."
if [[ "$1" != "--quiet" ]]; then
  echo ""
  echo "Press any key to close..."; read -k1
fi
