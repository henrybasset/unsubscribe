#!/bin/zsh
# Double-click this in Finder to run Unsubscribe once.
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found. Run 'xcode-select --install' once, then try again."
  echo "Press any key to close..."; read -k1; exit 1
fi
python3 unsubscribe.py "$@"
echo ""
echo "Done. Press any key to close this window..."
read -k1
