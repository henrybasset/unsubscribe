#!/usr/bin/env python3
"""
Gmail Unsubscribe — reach Gmail's Spam directly via the Gmail API.

Apple Mail does not sync Gmail's Spam folder over IMAP, so the Mail.app-based
unsubscribe.py can't see it. This talks to Google directly: it reads messages
labeled SPAM, unsubscribes via the List-Unsubscribe header, optionally moves
them to Trash, and logs the senders.

No third-party packages — OAuth2 (loopback + PKCE) and the Gmail REST API are
done with the standard library only.

One-time setup (creating your own Google OAuth client) is described in
GMAIL_SETUP.md. Put the downloaded client JSON at:
  ~/Library/Application Support/Unsubscribe/gmail_credentials.json

Usage:
  python3 gmail_unsubscribe.py            # unsubscribe from Spam senders
  python3 gmail_unsubscribe.py --dry-run  # list only, change nothing
  python3 gmail_unsubscribe.py --delete   # also move handled spam to Trash
"""

import os
import re
import sys
import csv
import json
import time
import base64
import hashlib
import webbrowser
import urllib.parse
import urllib.request
import urllib.error
from email.utils import parseaddr
from http.server import HTTPServer, BaseHTTPRequestHandler

STATE = os.environ.get("UNSUB_HOME") or os.path.expanduser(
    "~/Library/Application Support/Unsubscribe")
os.makedirs(STATE, exist_ok=True)
CREDS_PATH = os.path.join(STATE, "gmail_credentials.json")
TOKEN_PATH = os.path.join(STATE, "gmail_token.json")
CONFIG_PATH = os.path.join(STATE, "config.json")
SEEN_PATH = os.path.join(STATE, "gmail_seen.txt")   # unsubscribe URLs done
SPAM_PATH = os.path.join(STATE, "spammers.csv")
LOG_PATH = os.path.join(STATE, "gmail.log")

AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
API = "https://gmail.googleapis.com/gmail/v1/users/me"
SCOPE = "https://www.googleapis.com/auth/gmail.modify"  # read + trash

DRY_RUN = "--dry-run" in sys.argv
DELETE = "--delete" in sys.argv


def log(line):
    print(line)
    try:
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def b64url(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


# ---------------------------------------------------------------- config / state

def load_config():
    cfg = {"gmail_max": 200, "gmail_delete": False}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH) as f:
                data = json.load(f)
            for k in cfg:
                if k in data:
                    cfg[k] = data[k]
        except (ValueError, OSError):
            pass
    return cfg


def load_creds():
    if not os.path.exists(CREDS_PATH):
        return None
    with open(CREDS_PATH) as f:
        data = json.load(f)
    block = data.get("installed") or data.get("web") or data
    cid, secret = block.get("client_id"), block.get("client_secret")
    if cid and secret:
        return cid, secret
    return None


def load_seen():
    if not os.path.exists(SEEN_PATH):
        return set()
    with open(SEEN_PATH) as f:
        return {ln.strip() for ln in f if ln.strip()}


def mark_seen(url):
    with open(SEEN_PATH, "a") as f:
        f.write(url + "\n")


def append_spammers(rows):
    new_file = not os.path.exists(SPAM_PATH)
    with open(SPAM_PATH, "a", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["address", "name", "example_subject"])
        w.writerows(rows)


def load_spammers():
    known = set()
    if os.path.exists(SPAM_PATH):
        with open(SPAM_PATH, newline="") as f:
            for row in csv.reader(f):
                if row and "@" in row[0]:
                    known.add(row[0])
    return known


# ---------------------------------------------------------------- OAuth2

def http_post_form(url, fields):
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def oauth_flow(client_id, client_secret):
    verifier = b64url(os.urandom(48))
    challenge = b64url(hashlib.sha256(verifier.encode()).digest())
    captured = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if "code" in params:
                captured["code"] = params["code"][0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<h2>Unsubscribe: Google sign-in complete.</h2>"
                                 b"<p>You can close this tab.</p>")
            else:
                self.send_response(400)
                self.end_headers()

        def log_message(self, *a):
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    redirect = "http://127.0.0.1:%d/" % httpd.server_address[1]
    auth_url = AUTH_URI + "?" + urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": redirect,
        "response_type": "code", "scope": SCOPE,
        "code_challenge": challenge, "code_challenge_method": "S256",
        "access_type": "offline", "prompt": "consent",
    })
    log("Opening your browser for Google sign-in...")
    webbrowser.open(auth_url)
    log("If it didn't open, paste this URL into your browser:\n" + auth_url)
    while "code" not in captured:
        httpd.handle_request()  # ignores favicon etc., loops until the code
    tok = http_post_form(TOKEN_URI, {
        "client_id": client_id, "client_secret": client_secret,
        "code": captured["code"], "code_verifier": verifier,
        "grant_type": "authorization_code", "redirect_uri": redirect,
    })
    with open(TOKEN_PATH, "w") as f:
        json.dump({"refresh_token": tok.get("refresh_token")}, f)
    return tok["access_token"]


def get_access_token(client_id, client_secret):
    if os.path.exists(TOKEN_PATH):
        try:
            with open(TOKEN_PATH) as f:
                rt = json.load(f).get("refresh_token")
            if rt:
                tok = http_post_form(TOKEN_URI, {
                    "client_id": client_id, "client_secret": client_secret,
                    "refresh_token": rt, "grant_type": "refresh_token",
                })
                return tok["access_token"]
        except Exception:  # noqa: BLE001 - fall through to a fresh sign-in
            pass
    return oauth_flow(client_id, client_secret)


# ---------------------------------------------------------------- Gmail API

def api_get(path, token, params=None):
    url = API + path
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def api_post(path, token):
    req = urllib.request.Request(API + path, data=b"", method="POST",
                                 headers={"Authorization": "Bearer " + token})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def list_spam_ids(token, cap):
    ids, page = [], None
    while len(ids) < cap:
        params = {"labelIds": "SPAM", "maxResults": min(100, cap - len(ids))}
        if page:
            params["pageToken"] = page
        data = api_get("/messages", token, params)
        ids += [m["id"] for m in data.get("messages", [])]
        page = data.get("nextPageToken")
        if not page:
            break
    return ids[:cap]


def headers_of(token, msg_id):
    want = ["List-Unsubscribe", "List-Unsubscribe-Post", "From", "Subject"]
    data = api_get("/messages/" + msg_id, token,
                   {"format": "metadata", "metadataHeaders": want})
    out = {}
    for h in data.get("payload", {}).get("headers", []):
        out[h["name"].lower()] = h["value"]
    return out


def do_unsubscribe(https, one_click):
    headers = {"User-Agent": "Mozilla/5.0 (Unsubscribe; +Gmail helper)"}
    try:
        if one_click:
            req = urllib.request.Request(
                https, data=b"List-Unsubscribe=One-Click",
                headers={**headers, "Content-Type": "application/x-www-form-urlencoded"},
                method="POST")
            with urllib.request.urlopen(req, timeout=15) as r:
                return "one-click POST -> %s" % r.status, True
        req = urllib.request.Request(https, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=15) as r:
            return "GET -> %s (may need a manual confirm)" % r.status, True
    except urllib.error.HTTPError as e:
        return "http error %s" % e.code, False
    except Exception as e:  # noqa: BLE001
        return "failed: %s" % type(e).__name__, False


def main():
    mode = "DRY RUN — nothing will change" if DRY_RUN else "LIVE"
    log("\n=== Gmail Unsubscribe (%s) ===" % mode)

    creds = load_creds()
    if not creds:
        log("No Gmail credentials found.\n\n"
            "Set up a Google OAuth client (one time) — see GMAIL_SETUP.md — and "
            "save the downloaded JSON to:\n  %s" % CREDS_PATH)
        return
    cfg = load_config()
    delete = DELETE or bool(cfg.get("gmail_delete"))

    try:
        token = get_access_token(*creds)
    except Exception as e:  # noqa: BLE001
        log("Google sign-in failed: %s" % e)
        return

    ids = list_spam_ids(token, int(cfg.get("gmail_max", 200)))
    log("Gmail Spam messages: %d" % len(ids))

    seen = load_seen()
    known = load_spammers()
    new_spammers, done, nolink, errors, trashed = [], 0, 0, 0, 0

    for mid in ids:
        try:
            h = headers_of(token, mid)
        except Exception:  # noqa: BLE001
            errors += 1
            continue

        name, addr = parseaddr(h.get("from", ""))
        addr = addr.lower().strip()
        subject = (h.get("subject") or "(no subject)").strip()[:80]
        if addr and "@" in addr and addr not in known:
            known.add(addr)
            new_spammers.append([addr, name.strip(), subject])

        raw = h.get("list-unsubscribe", "")
        targets = re.findall(r"<([^>]+)>", raw)
        https = next((t for t in targets if t.lower().startswith("http")), None)
        one_click = "one-click" in h.get("list-unsubscribe-post", "").lower()

        if https and https not in seen:
            if DRY_RUN:
                log("  WOULD unsubscribe: %s | %s\n      -> %s" % (addr, subject, https))
                done += 1
            else:
                status, ok = do_unsubscribe(https, one_click)
                log("  unsubscribed: %s | %s\n      -> %s [%s]"
                    % (addr, subject, https, status))
                mark_seen(https)
                if ok:
                    done += 1
        elif not https:
            nolink += 1

        if delete and not DRY_RUN:
            try:
                api_post("/messages/%s/trash" % mid, token)
                trashed += 1
            except Exception:  # noqa: BLE001
                pass

    if new_spammers:
        append_spammers(new_spammers)

    log("\nSummary:")
    log("  unsubscribed (or would): %d" % done)
    log("  no unsubscribe link:     %d" % nolink)
    if delete:
        log("  moved to Trash:          %d" % trashed)
    log("  new spammer addresses:   %d" % len(new_spammers))
    log("  errors:                  %d" % errors)
    log("  log file: %s" % LOG_PATH)
    if DRY_RUN:
        log("\nThis was a dry run. Re-run without --dry-run to act for real.")


if __name__ == "__main__":
    main()
