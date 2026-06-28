# Google Calendar Setup Guide

Follow these steps once to connect the Learning Scheduler to your Google Calendar.

---

## Step 1 — Create a Google Cloud project

1. Go to [console.cloud.google.com](https://console.cloud.google.com/)
2. Click **New Project**, give it a name (e.g. `Learning Scheduler`), click **Create**
3. Make sure the new project is selected in the top bar

---

## Step 2 — Enable the Google Calendar API

1. In the left menu go to **APIs & Services → Library**
2. Search for **Google Calendar API** and click it
3. Click **Enable**

---

## Step 3 — Create OAuth 2.0 credentials

1. Go to **APIs & Services → Credentials**
2. Click **Create Credentials → OAuth client ID**
3. If prompted, configure the OAuth consent screen first:
   - User type: **External** (or Internal if using a Google Workspace account)
   - Fill in App name and your email; save
   - Under **Scopes** add `https://www.googleapis.com/auth/calendar`
   - Add your own email as a **Test user**
4. Back on Credentials, choose **Application type: Desktop app**
5. Click **Create** and then **Download JSON**

---

## Step 4 — Place the credentials file

Save the downloaded file as `credentials.json` in the project root:

```
Learning_Scheduler/
├── credentials.json   ← here
├── .env
├── src/
...
```

Then set the path in your `.env` file:

```
GOOGLE_CALENDAR_CREDENTIALS_FILE=credentials.json
```

---

## Step 5 — Authorize the app (first run)

On first startup, the scheduler will open a browser window asking you to sign in with your Google account and grant calendar access. After you approve, a `token.json` file is created in the project root and reused for all future runs.

```
Learning_Scheduler/
├── credentials.json
├── token.json         ← auto-created after first auth
```

Both files are excluded from git via `.gitignore`.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `FileNotFoundError: credentials.json not found` | Check the path in `GOOGLE_CALENDAR_CREDENTIALS_FILE` matches where you saved the file |
| `Error 403: access_denied` | Add your email as a test user in the OAuth consent screen |
| `Token has been expired or revoked` | Delete `token.json` and restart the server to re-authorize |
| Calendar events not appearing | Confirm the calendar ID is correct — the scheduler uses `primary` by default |

---

## Notes

- The app requests the `calendar` scope (read + write). It creates, reads, and deletes events within the scheduled week only.
- If you switch Google accounts, delete `token.json` and re-authorize.
- For production deployment (running unattended on a server), use a Service Account with domain-wide delegation instead of the OAuth Desktop flow above.
