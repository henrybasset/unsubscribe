# Unsubscribe

Auto-unsubscribe from junk mail on your Mac. **Unsubscribe** reads the messages
sitting in your macOS **Mail.app** Junk / Spam mailboxes and unsubscribes from
them using the standard [`List-Unsubscribe`](https://www.rfc-editor.org/rfc/rfc8058)
email header that legitimate senders include.

Everything runs **locally on your machine**. No accounts, no passwords, no
servers. The only network requests it makes are to the unsubscribe URLs the
senders themselves put in their emails.

## What it does

1. Asks Mail.app (via AppleScript) for the headers of every message in any
   mailbox named *Junk* or *Spam* — works for Apple Junk and Gmail Spam.
2. Parses the `List-Unsubscribe` / `List-Unsubscribe-Post` headers.
3. Unsubscribes:
   - **One-click** senders (RFC 8058) get a proper `POST`.
   - Others get a best-effort `GET` of the https link (some still want a click).
   - **Mailto-only** senders are logged and **skipped** — it never sends email
     from your account on your behalf.
4. **Flags** every junk message it acted on (a blue Mail flag) so you can see
   what was handled. Messages stay in Junk.
5. Records handled links in `seen.txt` so re-runs and the daily schedule skip
   work already done. Everything is logged to `log.txt`.

## Requirements

- macOS with **Mail.app** set up (your accounts already configured there).
- `python3` (preinstalled with Xcode Command Line Tools: `xcode-select --install`).

## Install as a Mac app

Build a real **Unsubscribe.app** and drop it in your Applications folder:

```sh
./build-app.command
```

This assembles `Unsubscribe.app` (bundling `unsubscribe.py`), generates the app
icon (`generate_icon.py` → `Unsubscribe.png` → `.icns`, no dependencies),
installs it to `/Applications` (or `~/Applications` if that isn't writable), and
ad-hoc signs it. Launch it from Finder or Spotlight like any other app — it
runs, then shows a summary dialog. State (what it's already done, plus logs) is
kept in `~/Library/Application Support/Unsubscribe/`.

It scans the Junk **and** Spam mailboxes of **every account** configured in
Mail.app. It never moves or deletes your mail — handled messages stay right
where they are in Junk, just marked with a blue flag.

Prefer not to build an app? You can run it directly instead:

## Use it

**Try it safely first** — a dry run changes nothing and just shows what it would do:

```sh
python3 unsubscribe.py --dry-run
```

**Run it for real:**

```sh
python3 unsubscribe.py
```

Or double-click **`Unsubscribe.command`** in Finder.

> First run, macOS asks for permission to let the script control Mail. Click
> **OK** (this is the standard Automation prompt) and run it again.

## Run it automatically (optional)

Double-click **`install-schedule.command`** to have it run quietly once a day at
09:00 via `launchd`.

Disable later:

```sh
launchctl unload ~/Library/LaunchAgents/com.local.unsubscribe.plist
rm ~/Library/LaunchAgents/com.local.unsubscribe.plist
```

## Notes & caveats

- Unsubscribe links in junk mail can themselves be tracking/confirmation pages.
  This tool only follows the official `List-Unsubscribe` header (not random body
  links), which is the safest signal available, but the web is the web — review
  `log.txt` to see exactly what was contacted.
- It never deletes or moves your mail; it only unsubscribes and flags.

## License

[MIT](LICENSE)
