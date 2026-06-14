#!/bin/zsh
# Build a distributable Unsubscribe.dmg (drag-to-Applications, with INSTALL.txt).
# Double-click this, or run it from a terminal. The .dmg lands on your Desktop.
#
# Note: the app is ad-hoc signed (not Apple-notarized), so people who download
# it will see a one-time Gatekeeper prompt — INSTALL.txt walks them through it.
set -e
cd "${0:A:h}"
REPO="$(pwd)"
APP="/Applications/Unsubscribe.app"

# Make sure we package the latest build.
echo "Building the app first..."
./build-app.command --quiet >/dev/null

STAGE="$(mktemp -d)/Unsubscribe!"
mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
cp "$REPO/INSTALL.txt" "$STAGE/"
ln -s /Applications "$STAGE/Applications"   # drag-to-install target

OUT="$HOME/Desktop/Unsubscribe.dmg"
rm -f "$OUT"
hdiutil create -volname "Unsubscribe!" -srcfolder "$STAGE" \
  -ov -format UDZO "$OUT" >/dev/null
rm -rf "$STAGE"

echo ""
echo "Created:  $OUT"
echo "Upload that file to GitHub Releases and/or your website."
if [[ "$1" != "--quiet" ]]; then
  echo ""
  echo "Press any key to close..."; read -k1
fi
