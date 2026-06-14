#!/usr/bin/env python3
"""
Triage — read recent Inbox mail with a LOCAL Ollama model and surface the
messages that need your personal action. Optional companion to Unsubscribe.

100% on-device: your email is sent only to Ollama on localhost. Nothing leaves
your Mac.

What it does:
  1. Pulls recent Inbox messages (all accounts) from Mail.app via AppleScript.
  2. Asks a local Ollama model (default llama3.1:latest) — with structured JSON
     output — whether each message needs you to personally do something.
  3. Marks the ones that do: either flags them, or moves them into a
     "Needs Action" mailbox (configurable). It NEVER deletes or archives mail,
     and it errs toward over-flagging rather than missing a real action item.

Config (optional): ~/Library/Application Support/Unsubscribe/config.json
  {
    "triage_days": 3,                 # how many days back to read
    "triage_mark": "flag",            # "flag" or "needs_action_mailbox"
    "triage_model": "llama3.1:latest",
    "triage_max": 50                  # safety cap on messages per run
  }

Usage:
  python3 triage.py            # classify and mark
  python3 triage.py --dry-run  # classify and report only, change nothing
"""

import os
import sys
import json
import time
import shutil
import subprocess
import urllib.request
import urllib.error
from email.utils import parseaddr

STATE = os.environ.get("UNSUB_HOME") or os.path.expanduser(
    "~/Library/Application Support/Unsubscribe")
os.makedirs(STATE, exist_ok=True)
CONFIG_PATH = os.path.join(STATE, "config.json")
SEEN_PATH = os.path.join(STATE, "triaged.txt")   # message-ids already triaged
LOG_PATH = os.path.join(STATE, "triage.log")
OLLAMA = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

FS = "\x1f"   # field separator (ASCII unit separator)
RS = "\x1e"   # record separator (ASCII record separator)

DRY_RUN = "--dry-run" in sys.argv

DEFAULTS = {
    "triage_days": 3,
    "triage_mark": "flag",            # safe default for everyone
    "triage_model": "llama3.1:latest",
    "triage_max": 50,
}

SCHEMA = {
    "type": "object",
    "properties": {
        "needs_action": {"type": "boolean"},
        "urgency": {"type": "string", "enum": ["low", "medium", "high"]},
        "reason": {"type": "string"},
    },
    "required": ["needs_action", "urgency", "reason"],
}

SYSTEM = (
    "You are an email triage assistant. Decide whether the user must PERSONALLY "
    "take an action on this email: reply, confirm, pay, sign, schedule, submit, "
    "or meet a deadline. Newsletters, promotions, marketing, receipts, "
    "shipping/order updates, social notifications, and automated alerts do NOT "
    "need action unless they explicitly require a personal response or have a "
    "real deadline for the user. Be conservative in the user's favor: if you are "
    "unsure whether it needs action, answer needs_action = true. Respond ONLY "
    "with the requested JSON."
)


def log(line):
    print(line)
    try:
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def load_config():
    cfg = dict(DEFAULTS)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH) as f:
                cfg.update({k: v for k, v in json.load(f).items() if k in DEFAULTS})
        except (ValueError, OSError):
            pass
    return cfg


def load_seen():
    if not os.path.exists(SEEN_PATH):
        return set()
    with open(SEEN_PATH) as f:
        return {ln.strip() for ln in f if ln.strip()}


def mark_seen(ids):
    with open(SEEN_PATH, "a") as f:
        for i in ids:
            f.write(i + "\n")


def run_osascript(script):
    try:
        return subprocess.run(["osascript", "-"], input=script,
                              capture_output=True, text=True, timeout=300)
    except FileNotFoundError:
        log("ERROR: osascript not found — is this macOS?")
        sys.exit(1)


def applescript_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def applescript_list(items):
    return "{" + ", ".join(applescript_str(i) for i in items) + "}"


def ollama_up():
    try:
        with urllib.request.urlopen(OLLAMA + "/api/tags", timeout=4) as r:
            json.load(r)
        return True
    except Exception:
        return False


def ollama_bin():
    for c in ("/opt/homebrew/bin/ollama", "/usr/local/bin/ollama", "/usr/bin/ollama"):
        if os.path.exists(c):
            return c
    return shutil.which("ollama")


def ensure_ollama_running():
    """Start the Ollama server if it isn't already up. Returns True if up."""
    if ollama_up():
        return True
    # Prefer the menu-bar Ollama.app (managed server); else `ollama serve`.
    if os.path.isdir("/Applications/Ollama.app"):
        subprocess.run(["open", "-a", "Ollama"], capture_output=True)
    else:
        b = ollama_bin()
        if b:
            subprocess.Popen([b, "serve"], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
    for _ in range(20):  # wait up to ~20s for it to come up
        if ollama_up():
            return True
        time.sleep(1)
    return ollama_up()


def have_model(model):
    try:
        with urllib.request.urlopen(OLLAMA + "/api/tags", timeout=4) as r:
            names = [m.get("name", "") for m in json.load(r).get("models", [])]
    except Exception:
        return False
    base = model.split(":")[0]
    return any(n == model or n.split(":")[0] == base for n in names)


def pull_model(model):
    """Download the model if it isn't present (one-time, can be a few GB)."""
    b = ollama_bin()
    if not b:
        return False
    log("Model %s not found — pulling it now (one-time, a few GB)..." % model)
    return subprocess.run([b, "pull", model]).returncode == 0


def ollama_classify(model, subject, sender, body):
    user = ("From: %s\nSubject: %s\n\nBody:\n%s"
            % (sender, subject, body[:2000]))
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user},
        ],
        "format": SCHEMA,
        "stream": False,
        "options": {"temperature": 0},
    }
    req = urllib.request.Request(
        OLLAMA + "/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=180) as r:
        resp = json.load(r)
    return json.loads(resp["message"]["content"])


FETCH = '''
on run
  set fsep to (ASCII character 31)
  set rsep to (ASCII character 30)
  set out to ""
  set cutoff to (current date) - (%d * days)
  tell application "Mail"
    set msgs to (messages of inbox whose date received is greater than or equal to cutoff)
    repeat with m in msgs
      try
        set bdy to ""
        try
          set bdy to content of m
        end try
        set out to out & (message id of m) & fsep & (sender of m) & fsep & (subject of m) & fsep & bdy & rsep
      end try
    end repeat
  end tell
  return out
end run
'''


def fetch_recent_inbox(days):
    proc = run_osascript(FETCH % days)
    if proc.returncode != 0:
        log("ERROR reading Inbox from Mail.app:\n" + proc.stderr.strip())
        log("\nTip: the first run needs permission to control Mail — approve "
            "the macOS prompt and run again.")
        sys.exit(1)
    records = [r for r in proc.stdout.split(RS) if r.strip()]
    out = []
    for r in records:
        parts = r.split(FS)
        if len(parts) < 4:
            continue
        mid, sender, subject, body = parts[0], parts[1], parts[2], FS.join(parts[3:])
        out.append({"message_id": mid.strip(), "sender": sender.strip(),
                    "subject": subject.strip(), "body": body})
    return out


def apply_marks(message_ids, mark):
    """Flag (orange) each Inbox message in the set; optionally move it to a
    local "Needs Action" mailbox."""
    if not message_ids:
        return
    move = (mark == "needs_action_mailbox")
    move_block = ""
    setup_block = ""
    if move:
        setup_block = '''
    if not (exists mailbox "Needs Action") then
      make new mailbox with properties {name:"Needs Action"}
    end if
    set nm to mailbox "Needs Action"'''
        move_block = "\n          move m to nm"
    # Look each message up fresh by its id (not a live filtered iteration): a
    # `move` shifts the inbox's indices, which would silently break subsequent
    # moves if we iterated a `whose` collection while mutating it.
    script = '''
on run
  set wanted to %s
  tell application "Mail"%s
    repeat with theId in wanted
      try
        set matches to (messages of inbox whose message id is theId)
        if matches is not {} then
          set m to item 1 of matches
          set flagged status of m to true
          set flag index of m to 1%s
        end if
      end try
    end repeat
  end tell
end run
''' % (applescript_list(list(message_ids)), setup_block, move_block)
    proc = run_osascript(script)
    if proc.returncode != 0:
        log("  (note: could not mark messages: %s)" % proc.stderr.strip())


def main():
    cfg = load_config()
    mode = "DRY RUN — nothing will change" if DRY_RUN else "LIVE"
    log("\n=== Triage (%s) — model %s ===" % (mode, cfg["triage_model"]))

    model = cfg["triage_model"]
    if not ensure_ollama_running():
        if not ollama_bin():
            log("Ollama isn't installed. Install it from https://ollama.com, "
                "then try Triage again.")
        else:
            log("Couldn't start Ollama. Open the Ollama app (or run "
                "`ollama serve`) and try Triage again.")
        return
    if not have_model(model):
        if not pull_model(model):
            log("Model %s is unavailable and the download failed.\n"
                "Run:  ollama pull %s" % (model, model))
            return

    msgs = fetch_recent_inbox(cfg["triage_days"])
    seen = load_seen()
    fresh = [m for m in msgs if m["message_id"] and m["message_id"] not in seen]
    fresh = fresh[:cfg["triage_max"]]
    log("Inbox messages in last %d day(s): %d  (new to triage: %d)"
        % (cfg["triage_days"], len(msgs), len(fresh)))

    action_ids = []
    triaged_ids = []
    errors = 0
    for m in fresh:
        try:
            verdict = ollama_classify(
                cfg["triage_model"], m["subject"], m["sender"], m["body"])
        except Exception as e:  # noqa: BLE001
            errors += 1
            log("  ? classify failed (%s): %s" % (type(e).__name__, m["subject"][:60]))
            continue
        triaged_ids.append(m["message_id"])
        if verdict.get("needs_action"):
            action_ids.append(m["message_id"])
            log("  ACTION [%s] %s — %s | %s"
                % (verdict.get("urgency", "?"),
                   parseaddr(m["sender"])[1] or m["sender"], m["subject"][:60],
                   verdict.get("reason", "")[:80]))

    if not DRY_RUN:
        if action_ids:
            apply_marks(action_ids, cfg["triage_mark"])
        if triaged_ids:
            mark_seen(triaged_ids)  # don't re-classify next run

    where = ("moved to the \"Needs Action\" mailbox"
             if cfg["triage_mark"] == "needs_action_mailbox" else "flagged (orange)")
    log("\nSummary:")
    log("  needs action: %d  (%s)" % (len(action_ids),
                                      "preview only" if DRY_RUN else where))
    log("  classified:   %d" % len(triaged_ids))
    log("  errors:       %d" % errors)
    log("  log file: %s" % LOG_PATH)
    if DRY_RUN:
        log("\nThis was a dry run. Re-run without --dry-run to mark for real.")


if __name__ == "__main__":
    main()
