# RunTwin self-hosted setup guide

**English** | [繁體中文](DISTRIBUTION-SOP.zh-TW.md)

This guide is for a runner who wants to run their own RunTwin on a Windows PC, connected to their own Strava account. The repository contains nobody's accounts, activities, databases, tokens, API keys, or training goals. The commands below use PowerShell. On macOS or Linux, replace `.venv\Scripts\python.exe` with `.venv/bin/python`.

## 0. Requirements

> Privacy note: after publishing, each Strava activity description contains a RunTwin analysis block. Its marker is set by `RUNTWIN_ANALYSIS_LABEL`. If you don't want others to see it, set those activities to Only Me in Strava, or don't run the publishing commands.

### Required

- Windows 10/11 (macOS/Linux also work)
- Python 3.11 or 3.12
- Git (`git clone` this repository), or download the ZIP from GitHub
- A Strava account
- For automatic Strava sync: a Strava API application created under your own account

Under Strava's current rules, the account that creates an API application needs a Strava subscription. Without the Strava API, you can still try RunTwin with the anonymous fixture or your own snapshot.

### Optional

- An Anthropic or OpenAI API key, for richer LLM-written analysis. Without one, the rule-based fallback is used.
- Docker Desktop, for PostgreSQL and always-on services. For a first try, the local mode below is simpler.
- A public HTTPS domain or tunnel, which is only needed for real-time webhooks. Without it, the worker still picks up new runs every hour.

## 1. Get the source

```powershell
git clone https://github.com/<your-account>/runtwin.git C:\RunTwin
Set-Location C:\RunTwin
```

Or download the ZIP and extract it somewhere without special permission restrictions, such as `C:\RunTwin`.

## 2. Create a Python environment

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

If you don't have Python 3.12, use `py -3.11 -m venv .venv`.

## 3. Create your own `.env`

```powershell
Copy-Item .env.example .env
```

Generate a Django secret:

```powershell
.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(64))"
```

For local mode, set at least:

```dotenv
DJANGO_SECRET_KEY=paste-the-generated-value
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000
DATABASE_URL=
RUNTWIN_PROVIDER=strava_api
RUNTWIN_EXPORT_DIR=runtime/exports
STRAVA_TOKEN_FILE=runtime/strava-token.json

RUNTWIN_ADMIN_USERNAME=runner
RUNTWIN_ADMIN_PASSWORD=change-to-your-own-long-random-password
RUNTWIN_ADMIN_EMAIL=
```

`.env` holds passwords and tokens. Never upload it, share it, or commit it. It is already in `.gitignore`.

## 4. Create your own Strava API application

1. Sign in to Strava and open <https://www.strava.com/settings/api>.
2. Create an application. The website can be any description URL for local use.
3. Set **Authorization Callback Domain** to `localhost`.
4. Note your Client ID and Client Secret.
5. The OAuth scopes must include:
   - `activity:read_all`, to read activities including Only Me ones.
   - `activity:write`, to publish `[Easy]`/`[Long]` title tags and the analysis block.

Then run the bundled OAuth helper:

```powershell
.venv\Scripts\python.exe scripts\configure_strava_oauth.py
```

Enter your Client ID and Client Secret when prompted. The helper:

1. opens the Strava authorization page,
2. receives the one-time code at `http://localhost:8765/callback`,
3. exchanges it for tokens,
4. writes your client ID, client secret, refresh token, and athlete ID into `.env`.

Afterwards `.env` contains:

```dotenv
STRAVA_CLIENT_ID=your-client-id
STRAVA_CLIENT_SECRET=your-client-secret
STRAVA_REFRESH_TOKEN=your-refresh-token
STRAVA_ATHLETE_ID=your-numeric-athlete-id
```

If a firewall blocks the local callback, get a refresh token manually by following Strava's OAuth docs: <https://developers.strava.com/docs/authentication/>.

## 5. Configure AI analysis (optional)

Pick one provider and use your own API key.

Anthropic (Claude), with a key from <https://console.anthropic.com/>:

```dotenv
RUNTWIN_AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-your-key
RUNTWIN_AI_MODEL=
```

OpenAI, with a key from <https://platform.openai.com/api-keys>:

```dotenv
RUNTWIN_AI_PROVIDER=openai
OPENAI_API_KEY=sk-your-key
RUNTWIN_AI_MODEL=
```

With `RUNTWIN_AI_MODEL` empty, the default model is used: `claude-opus-5-5` for Anthropic, `gpt-6.2-astra` for OpenAI. To reduce cost, use `claude-sonnet-5-5` or `gpt-6.2-sol`.

To run without AI, leave `RUNTWIN_AI_PROVIDER` empty and the deterministic fallback is used.

## 6. Initialize the database and login

```powershell
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py seed_athlete_profile
.venv\Scripts\python.exe manage.py create_local_user
```

`seed_athlete_profile` only creates an empty profile with no personal data.

After starting the web app (step 8), sign in to Django admin at <http://127.0.0.1:8000/admin/>. Open **Athlete profiles** and fill in your own values:

- time zone
- half-marathon PB and goal
- marathon goal
- usual weekly distance
- runs per week
- weekday single-run distance limit
- long-run days
- provisional tempo HR range
- observed max HR

Don't copy someone else's numbers. You can leave unknown fields empty. If you don't know your usual weekly distance or weekday limit, enter `0`.

## 7. First sync and test

Sync your Strava activities:

```powershell
.venv\Scripts\python.exe manage.py sync_strava_activities
```

Scan the last 14 days, analyze unpublished runs, and publish them to Strava:

```powershell
.venv\Scripts\python.exe manage.py reconcile_strava_activities --days 14 --limit 100
```

Note that `reconcile_strava_activities` **modifies** Strava titles and descriptions. To preview an existing local analysis for one activity first:

```powershell
.venv\Scripts\python.exe manage.py publish_activity_analysis <activity-id> --dry-run
```

## 8. Start the three services

Open three PowerShell windows in `C:\RunTwin`.

**Window A, web app:**

```powershell
.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --noreload
```

Then open <http://127.0.0.1:8000/weekly>.

**Window B, new-activity worker:**

```powershell
.venv\Scripts\python.exe manage.py process_strava_webhooks
```

Even without a public webhook, the worker re-scans the last 14 days (`STRAVA_RECONCILE_DAYS`) every hour to pick up new runs. If your PC was off for longer than that, run `reconcile_strava_activities --days N` manually.

**Window C, daily weekly-report scheduler:**

```powershell
.venv\Scripts\python.exe manage.py run_weekly_scheduler
```

This refreshes the current week's report at 09:00 Asia/Taipei every day, and finalizes the previous week on Mondays.

Closing a window stops that service. To start everything on boot, use Docker Compose (step 10) or a Windows Scheduled Task or service.

## 9. Real-time webhook mode (advanced, optional)

Without a webhook, new runs appear within one reconcile interval (one hour by default). For near-instant processing you need:

1. A stable public HTTPS URL.
2. Two independent random tokens:

   ```powershell
   .venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

3. These values in `.env`:

   ```dotenv
   STRAVA_WEBHOOK_PATH_TOKEN=first-random-value
   STRAVA_WEBHOOK_VERIFY_TOKEN=second-random-value
   STRAVA_WEBHOOK_CALLBACK_URL=https://your-domain/webhooks/strava/first-random-value
   STRAVA_WEBHOOK_SUBSCRIPTION_ID=
   ```

   Add the public hostname to `DJANGO_ALLOWED_HOSTS`.

4. Confirm the public `/healthz` endpoint is reachable.
5. Create the subscription:

   ```powershell
   .venv\Scripts\python.exe manage.py manage_strava_webhook create
   ```

6. Put the returned ID in `STRAVA_WEBHOOK_SUBSCRIPTION_ID=`.
7. Restart the web app and the worker.

## 10. Docker mode (optional)

1. Install and start Docker Desktop.
2. In `.env`, use the container paths:

   ```dotenv
   DATABASE_URL=postgresql://runtwin:your-db-password@db:5432/runtwin
   RUNTWIN_EXPORT_DIR=/app/runtime/exports
   STRAVA_TOKEN_FILE=/app/runtime/strava-token.json
   POSTGRES_PASSWORD=your-db-password
   DJANGO_SECRET_KEY=long-random-string
   ```

   Compose refuses to start if `POSTGRES_PASSWORD` or `DJANGO_SECRET_KEY` is missing.

3. Start:

   ```powershell
   docker compose up --build -d
   docker compose ps
   ```

4. Create a login:

   ```powershell
   docker compose exec web python manage.py create_local_user
   ```

Compose runs PostgreSQL, the web app, the worker, and the daily scheduler. A public webhook still needs an HTTPS reverse proxy or tunnel.

## 11. Verify and troubleshoot

```powershell
.venv\Scripts\python.exe manage.py check
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/healthz   # expect {"status":"ok"}
.venv\Scripts\python.exe -m pytest                                   # never calls Strava, Garmin, or any LLM
```

Common issues:

- **LLM `401`**: `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` is wrong, or doesn't match `RUNTWIN_AI_PROVIDER`. Runs fall back to the deterministic analysis.
- **Strava `401`**: the refresh token or client ID/secret is wrong, or the token was revoked.
- **Nothing gets published**: the OAuth grant is missing `activity:write`.
- **Only Me activities are missing**: the OAuth grant is missing `activity:read_all`.
- **A new activity doesn't show up**: make sure the worker is running, or run reconciliation manually.
- **`.env` changes have no effect**: restart the web app, the worker, and the scheduler.
- **SQLite `database is locked`**: don't start multiple workers or servers. For long-term use, switch to Docker PostgreSQL.

## 12. Security checklist

Before sharing, backing up, or reporting an issue, never attach:

- `.env`
- `db.sqlite3`
- `runtime/strava-token.json`
- `runtime/` logs and exports
- `snapshots/`
- screenshots showing personal data
- your client secret, refresh token, or Anthropic/OpenAI key

For deployment models and multi-user considerations, see [`docs/sharing-and-deployment.md`](docs/sharing-and-deployment.md) (Chinese).
