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
- A Garmin Connect account, if you also record runs on a Garmin watch (step 7).
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

## 4. Connect Strava

RunTwin talks to Strava through **your own** Strava API application. You create it once, then authorize it to access your account.

### 4.1 Create the API application

1. Sign in to Strava in a browser and open <https://www.strava.com/settings/api>.
2. Fill in the form:
   | Field | What to enter |
   |---|---|
   | Application Name | Anything, e.g. `My RunTwin` |
   | Category | `Training` (any category works) |
   | Website | Any URL, e.g. `http://localhost` |
   | Authorization Callback Domain | `localhost` (exactly this; no `http://`, no port) |
3. Upload an icon if Strava asks for one (any image works), and agree to the API terms.
4. On the app page, copy the **Client ID** (a number) and the **Client Secret** (click *show*). Treat the secret like a password.

### 4.2 Authorize your account

Run the bundled helper from the RunTwin folder:

```powershell
.venv\Scripts\python.exe scripts\configure_strava_oauth.py
```

1. Paste your Client ID and Client Secret when prompted.
2. A browser opens the Strava consent page. **Keep both permission checkboxes ticked**, then click **Authorize**:
   - *View data about your private activities* (`activity:read_all`), so RunTwin can read all your runs, including Only Me ones.
   - *Upload your activities … to Strava* (`activity:write`), so RunTwin can add `[Easy]`/`[Long]` title tags and the analysis block.
3. The browser shows *"Strava authorization received. You can close this window."*
4. The terminal prints `Updated .env with this athlete's Strava OAuth settings.`

The helper waits 5 minutes for the redirect. It writes these to `.env`:

```dotenv
STRAVA_CLIENT_ID=your-client-id
STRAVA_CLIENT_SECRET=your-client-secret
STRAVA_REFRESH_TOKEN=your-refresh-token
STRAVA_ATHLETE_ID=your-numeric-athlete-id
```

RunTwin refreshes the access token automatically from then on and saves rotated tokens to `STRAVA_TOKEN_FILE`. You don't need to repeat this step unless you revoke access.

### 4.3 Check the connection

```powershell
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py sync_strava_activities
```

If this ends without an error and reports imported activities, Strava is connected.

### 4.4 If something goes wrong

| Symptom | Fix |
|---|---|
| Strava page says `redirect_uri invalid` | Authorization Callback Domain must be exactly `localhost`. |
| `Authorization is missing required permissions` | You unticked a checkbox. Run the helper again and keep both ticked. |
| `Timed out waiting for the Strava redirect` | Run the helper again and finish within 5 minutes. |
| Browser can't open `localhost:8765` | Another program is using port 8765, or a firewall blocks it. Run with `--redirect-uri http://localhost:8766/callback`. |
| No browser available (server, SSH) | Run with `--no-browser`, open the printed URL on any device signed in to Strava, then copy the final `localhost` address from that browser and open it on the RunTwin machine. Or follow Strava's manual OAuth steps: <https://developers.strava.com/docs/authentication/>. |
| `sync_strava_activities` returns `401` | Wrong client secret, or access was revoked. Run the helper again. |

To disconnect RunTwin later, revoke it at <https://www.strava.com/settings/apps>.

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

After starting the web app (step 9), sign in to Django admin at <http://127.0.0.1:8000/admin/>. Open **Athlete profiles** and fill in your own values:

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

## 7. Connect Garmin (optional)

Strava stays the main data source. If you also record runs with a Garmin watch, RunTwin can add Garmin-only metrics to each analysis: training effect, training load, HR zones, running dynamics, Body Battery, VO2max, and weather. Without Garmin everything still works.

> Garmin Connect has no official API for personal projects. RunTwin uses the unofficial `garminconnect` package, which can break when Garmin changes its login. Garmin failures never block Strava analysis.

### 7.1 Sign in once

```powershell
.venv\Scripts\python.exe scripts\configure_garmin_auth.py
```

1. Enter your Garmin Connect email and password. The password is used once and never saved.
2. If your account has two-step verification, enter the code Garmin sends you at the `Garmin MFA code:` prompt.
3. The terminal prints `Garmin tokens saved to ...` and `Updated .env: RUNTWIN_GARMIN_ENABLED=1 ...`.

Tokens are saved to `~/.garminconnect` (on Windows, `C:\Users\<you>\.garminconnect`). That folder grants access to your Garmin account, so keep it private and never commit it. Useful options: `--token-dir <folder>` for another location, `--is-cn` for Garmin Connect China accounts, and `--no-env` to leave `.env` unchanged.

### 7.2 How matching works

For each Strava run, RunTwin looks for a Garmin running activity that started within ±120 seconds and whose distance differs by at most 5%. Matched metrics are stored in `Activity.garmin_metrics` and passed to the analysis. Unmatched runs simply have no Garmin data.

### 7.3 Check the connection

After the first sync (step 8), open a recent run at `http://127.0.0.1:8000/activities/<id>`. When a match was found, the analysis mentions Garmin training effect or HR zones. Garmin problems only show up as warnings in the worker output, for example `Garmin metrics unavailable`.

### 7.4 Docker

The worker and scheduler mount the host folder `RUNTWIN_GARMIN_HOST_TOKEN_DIR` (default `~/.garminconnect`). Run the script on the host first, then set `RUNTWIN_GARMIN_ENABLED=1` in `.env` and restart Compose.

### 7.5 If something goes wrong

| Symptom | Fix |
|---|---|
| `Garmin login failed` while running the script | Check your email and password. Sign in once at <https://connect.garmin.com> in a browser to clear any security prompt, then retry. |
| Worker logs `Garmin metrics unavailable` | Tokens expired or were revoked. Run `configure_garmin_auth.py` again. |
| No Garmin data on a run | The run wasn't recorded on Garmin, or its start time or distance differs too much from the Strava copy. |
| You want to turn Garmin off | Set `RUNTWIN_GARMIN_ENABLED=0` and restart. You can delete the token folder. |

## 8. First sync and test

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

## 9. Start the three services

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

Closing a window stops that service. To start everything on boot, use Docker Compose (step 11) or a Windows Scheduled Task or service.

## 10. Real-time webhook mode (advanced, optional)

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

## 11. Docker mode (optional)

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

## 12. Verify and troubleshoot

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

## 13. Security checklist

Before sharing, backing up, or reporting an issue, never attach:

- `.env`
- `db.sqlite3`
- `runtime/strava-token.json`
- `runtime/` logs and exports
- `snapshots/`
- screenshots showing personal data
- the Garmin token folder (`~/.garminconnect`)
- your client secret, refresh token, or Anthropic/OpenAI key

For deployment models and multi-user considerations, see [`docs/sharing-and-deployment.md`](docs/sharing-and-deployment.md) (Chinese).
