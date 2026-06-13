#!/usr/bin/env python3
"""
Unsubscribe — auto-unsubscribe from messages sitting in your macOS Mail.app
Junk / Spam mailboxes, using the standard List-Unsubscribe email header.

How it works:
  1. Asks Mail.app (via AppleScript) for the raw headers of every message in
     any mailbox named "Junk" or "Spam".
  2. Parses the RFC 2369 / RFC 8058 List-Unsubscribe header.
  3. For "one-click" senders it POSTs the unsubscribe (RFC 8058). Otherwise it
     GETs the https unsubscribe link (best effort — some still need a click).
     Mailto-only senders are logged and skipped (we never send mail for you).
  4. Flags every junk message it acted on (a colored Mail flag) so you can see
     what was handled. The message stays in Junk.
  5. Remembers what it already did (seen.txt) so re-runs are cheap and safe.

Everything happens locally. No credentials are stored or sent anywhere except
to the unsubscribe URLs the senders themselves put in their emails.

Usage:
  python3 unsubscribe.py            # do it for real
  python3 unsubscribe.py --dry-run  # show what it WOULD do, change nothing
"""

import os
import re
import sys
import json
import subprocess
import urllib.request
import urllib.error
from email.parser import Parser

# Repo-relative state, so it works wherever the repo is cloned.
BASE = os.path.dirname(os.path.abspath(__file__))
SEEN_PATH = os.path.join(BASE, "seen.txt")
LOG_PATH = os.path.join(BASE, "log.txt")
SEP = "@@@MSGSEP@@@"
FLAG_COLOR_INDEX = 4  # macOS Mail flag colors: 0 red .. 6; 4 = blue

DRY_RUN = "--dry-run" in sys.argv

# Pass 1: dump raw headers of every Junk/Spam message (Message-ID is in them).
READ_SCRIPT = r'''
on run
  set sep to "
@@@MSGSEP@@@
"
  set output to ""
  tell application "Mail"
    set candidates to {}
    try
      set candidates to candidates & (every mailbox)
    end try
    repeat with acct in accounts
      try
        set candidates to candidates & (every mailbox of acct)
      end try
    end repeat
    repeat with mb in candidates
      set nm to ""
      try
        set nm to name of mb
      end try
      if (nm contains "junk") or (nm contains "spam") then
        try
          repeat with msg in (messages of mb)
            try
              set output to output & (all headers of msg) & sep
            end try
          end repeat
        end try
      end if
    end repeat
  end tell
  return output
end run
'''


def log(line):
    print(line)
    try:
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def load_seen():
    if not os.path.exists(SEEN_PATH):
        return set()
    with open(SEEN_PATH) as f:
        return {ln.strip() for ln in f if ln.strip()}


def mark_seen(key):
    with open(SEEN_PATH, "a") as f:
        f.write(key + "\n")


def run_osascript(script, **kwargs):
    try:
        return subprocess.run(
            ["osascript", "-"], input=script,
            capture_output=True, text=True, timeout=180, **kwargs,
        )
    except FileNotFoundError:
        log("ERROR: osascript not found — is this macOS?")
        sys.exit(1)


def fetch_junk_headers():
    """Return a list of raw header blocks, one per junk/spam message."""
    proc = run_osascript(READ_SCRIPT)
    if proc.returncode != 0:
        log("ERROR talking to Mail.app:\n" + proc.stderr.strip())
        log("\nTip: the first run needs permission. When macOS asks to let "
            "this control Mail, click OK, then run again.")
        sys.exit(1)
    blocks = [b.strip() for b in proc.stdout.split(SEP)]
    return [b for b in blocks if b]


def parse_unsub(block):
    """Return dict with subject, sender, message-id, https, one_click, mailto."""
    msg = Parser().parsestr(block, headersonly=True)
    raw = msg.get("List-Unsubscribe", "")
    post = msg.get("List-Unsubscribe-Post", "")
    targets = re.findall(r"<([^>]+)>", raw)
    https = next((t for t in targets if t.lower().startswith("http")), None)
    mailto = next((t for t in targets if t.lower().startswith("mailto:")), None)
    return {
        "subject": (msg.get("Subject") or "(no subject)").strip()[:80],
        "sender": (msg.get("From") or "?").strip()[:80],
        "message_id": (msg.get("Message-ID") or msg.get("Message-Id") or "").strip(),
        "https": https,
        "mailto": mailto,
        "one_click": "one-click" in post.lower(),
    }


def do_unsubscribe(info):
    """Perform the https unsubscribe. Returns a short status string."""
    url = info["https"]
    headers = {"User-Agent": "Mozilla/5.0 (Unsubscribe; +macOS Mail helper)"}
    try:
        if info["one_click"]:
            req = urllib.request.Request(
                url, data=b"List-Unsubscribe=One-Click",
                headers={**headers,
                         "Content-Type": "application/x-www-form-urlencoded"},
                method="POST")
            with urllib.request.urlopen(req, timeout=15) as r:
                return f"one-click POST -> {r.status}", True
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=15) as r:
            return f"GET -> {r.status} (may need a manual confirm click)", True
    except urllib.error.HTTPError as e:
        return f"http error {e.code}", False
    except Exception as e:  # noqa: BLE001 - best effort, never crash the run
        return f"failed: {type(e).__name__}", False


def flag_handled(message_ids):
    """Pass 2: flag every Junk/Spam message whose Message-ID we acted on."""
    if not message_ids:
        return
    ids_json = json.dumps(list(message_ids))
    script = '''
on run
  set wanted to ''' + applescript_list(message_ids) + '''
  tell application "Mail"
    set candidates to {}
    try
      set candidates to candidates & (every mailbox)
    end try
    repeat with acct in accounts
      try
        set candidates to candidates & (every mailbox of acct)
      end try
    end repeat
    repeat with mb in candidates
      set nm to ""
      try
        set nm to name of mb
      end try
      if (nm contains "junk") or (nm contains "spam") then
        try
          repeat with msg in (messages of mb)
            try
              set mid to message id of msg
              if wanted contains mid then
                set flagged status of msg to true
                set flag index of msg to ''' + str(FLAG_COLOR_INDEX) + '''
              end if
            end try
          end repeat
        end try
      end if
    end repeat
  end tell
end run
'''
    proc = run_osascript(script)
    if proc.returncode != 0:
        log("  (note: could not flag handled messages: %s)"
            % proc.stderr.strip())
    _ = ids_json  # kept for debugging/logging parity


def applescript_list(items):
    """Build an AppleScript list literal of quoted strings."""
    def esc(s):
        return s.replace("\\", "\\\\").replace('"', '\\"')
    return "{" + ", ".join('"%s"' % esc(i) for i in items) + "}"


def main():
    mode = "DRY RUN — nothing will change" if DRY_RUN else "LIVE"
    log("\n=== Unsubscribe (%s) ===" % mode)

    blocks = fetch_junk_headers()
    log("Found %d message(s) in Junk/Spam." % len(blocks))

    seen = load_seen()
    handled_ids = set()
    done = mailto_only = nolink = already = 0

    for block in blocks:
        info = parse_unsub(block)

        if not info["https"] and not info["mailto"]:
            nolink += 1
            continue

        if not info["https"] and info["mailto"]:
            mailto_only += 1
            log("  ~ mailto-only, skipped: %s | %s"
                % (info["sender"], info["subject"]))
            continue

        key = info["https"]
        if key in seen:
            already += 1
            continue

        if DRY_RUN:
            log("  WOULD unsubscribe: %s | %s\n      -> %s%s"
                % (info["sender"], info["subject"], key,
                   " [one-click]" if info["one_click"] else ""))
            done += 1
            continue

        status, ok = do_unsubscribe(info)
        log("  unsubscribed: %s | %s\n      -> %s [%s]"
            % (info["sender"], info["subject"], key, status))
        mark_seen(key)
        done += 1
        if ok and info["message_id"]:
            handled_ids.add(info["message_id"])

    if not DRY_RUN and handled_ids:
        log("Flagging %d handled message(s) in Mail..." % len(handled_ids))
        flag_handled(handled_ids)

    log("\nSummary:")
    log("  unsubscribed (or would): %d" % done)
    log("  already handled before:  %d" % already)
    log("  mailto-only skipped:     %d" % mailto_only)
    log("  no unsubscribe link:     %d" % nolink)
    log("  log file: %s" % LOG_PATH)
    if DRY_RUN:
        log("\nThis was a dry run. Re-run without --dry-run to do it for real.")


if __name__ == "__main__":
    main()
