# Gmail setup (one time)

Apple Mail doesn't sync Gmail's **Spam** folder over IMAP, so `gmail_unsubscribe.py`
talks to Google directly via the Gmail API. To do that it needs **your own**
Google OAuth client (free, ~5 minutes). Everything stays on your Mac — your
client credentials and tokens live only in
`~/Library/Application Support/Unsubscribe/`.

## 1. Create a Google Cloud project
1. Go to <https://console.cloud.google.com/> and sign in with the Gmail account
   you want to clean (e.g. `henrybasset@gmail.com`).
2. Click the project picker (top bar) → **New Project** → name it `Unsubscribe`
   → **Create**, then make sure it's the selected project.

## 2. Enable the Gmail API
1. Go to **APIs & Services → Library** (or <https://console.cloud.google.com/apis/library/gmail.googleapis.com>).
2. Search **Gmail API** → open it → **Enable**.

## 3. Configure the consent screen
1. **APIs & Services → OAuth consent screen**.
2. User type **External** → **Create**.
3. Fill app name (`Unsubscribe`), your email for the support + developer
   contact fields → **Save and Continue**.
4. **Scopes**: you can skip adding scopes here → **Save and Continue**.
5. **Test users**: click **Add Users**, add your own Gmail address →
   **Save and Continue**. (While the app is "Testing", only listed test users
   can use it — that's fine for personal use.)

## 4. Create the OAuth client
1. **APIs & Services → Credentials → Create Credentials → OAuth client ID**.
2. Application type **Desktop app** → name it `Unsubscribe` → **Create**.
3. Click **Download JSON** on the client you just made.

## 5. Drop the file in place
Save that downloaded file as:

```
~/Library/Application Support/Unsubscribe/gmail_credentials.json
```

(That folder already exists once you've run Unsubscribe at least once.)

## 6. Run it
From the menu bar: **Gmail: Unsubscribe from Spam** — or in a terminal:

```sh
python3 ~/unsubscribe/gmail_unsubscribe.py --dry-run   # preview
python3 ~/unsubscribe/gmail_unsubscribe.py             # do it
python3 ~/unsubscribe/gmail_unsubscribe.py --delete    # also Trash the spam
```

The first run opens your browser to sign in and grant access. You'll see an
"unverified app" warning (because it's your own personal client) — click
**Advanced → Go to Unsubscribe (unsafe)** to continue; this is expected for a
self-made client. After that, a refresh token is stored locally and you won't
need to sign in again.

## Scope used
`https://www.googleapis.com/auth/gmail.modify` — read messages and move them to
Trash. It never permanently deletes, and the unsubscribe requests only go to the
URLs senders put in their own `List-Unsubscribe` headers.
