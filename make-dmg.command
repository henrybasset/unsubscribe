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
rm -f "$OUT" "$OUT.sha256" "$OUT.asc"
hdiutil create -volname "Unsubscribe!" -srcfolder "$STAGE" \
  -ov -format UDZO "$OUT" >/dev/null
rm -rf "$STAGE"

# SHA-256 checksum (always) — lets anyone verify the download is intact.
( cd "$(dirname "$OUT")" && shasum -a 256 "$(basename "$OUT")" > "$(basename "$OUT").sha256" )

# GPG detached signature (only if you have a signing key) — proves it's from you.
if command -v gpg >/dev/null 2>&1 && [ -n "$(gpg --list-secret-keys 2>/dev/null)" ]; then
  gpg --armor --detach-sign --output "$OUT.asc" "$OUT"
  SIGNED="yes"
else
  SIGNED="no (no GPG key found — see README 'Verify your download')"
fi

echo ""
echo "Created:   $OUT"
echo "Checksum:  $OUT.sha256"
echo "Signed:    $SIGNED"
echo ""
echo "Upload the .dmg, the .sha256, and (if present) the .asc to GitHub Releases."
if [[ "$1" != "--quiet" ]]; then
  echo ""
  echo "Press any key to close..."; read -k1
fi
