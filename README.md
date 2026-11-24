# RunTwin

**English** | [繁體中文](README.zh-TW.md)

Self-hosted running analytics for Strava. RunTwin syncs your runs through your own Strava OAuth app, classifies each workout with deterministic rules, computes weekly facts (volume, long runs, quality sessions, HR drift, pace-to-HR efficiency), and can write a short coaching note back into each activity's description. An LLM is optional: plug in **Anthropic (Claude)** or **OpenAI** with your own API key, or run fully deterministic.

> Step-by-step Windows setup with your own Strava account: [`DISTRIBUTION-SOP.md`](DISTRIBUTION-SOP.md). This repository contains no personal accounts, activities, tokens, API keys, or databases.
>
> Generated reports and coaching notes are written in Traditional Chinese (zh-TW).

**Quick start (no Strava account needed):**

```bash
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate && python manage.py seed_athlete_profile
python manage.py import_mcp_snapshot fixtures/anonymous_mcp_snapshot.json
python manage.py generate_weekly_report --week 2026-08-24
RUNTWIN_ADMIN_USERNAME=runner RUNTWIN_ADMIN_PASSWORD='change-me-long-random' python manage.py create_local_user
python manage.py runserver           # open http://localhost:8000/weekly
```

All numbers are computed by deterministic Python analytics. When enabled, the LLM only explains clean, pre-computed facts. It never reads raw streams, and it never estimates LT1/LT2 or predicts race results.

## Features

- Strava-compatible provider boundary: import an MCP snapshot, or sync through your own Strava OAuth app.
- Activity/stream normalization, idempotent upserts, and data-quality scoring.
- Rule- and stream-based workout classification (Easy, Recovery, Long, Tempo, Threshold, Intervals, Fartlek, Progression, Race), with confidence, reasons, and version.
- Full Asia/Taipei weeks, with comparisons to the previous week, the 4-week average, and a 6-week trend.
- Distance, time, elevation, long runs, quality sessions, HR/pace coverage, steady-run HR drift, and pace-to-HR efficiency.
- Fixed-schema weekly report, per-activity evidence, a wellbeing check-in, and a responsive dashboard.
- Optional LLM analysis via the official Anthropic or OpenAI API, with automatic deterministic fallback.
- PostgreSQL, Docker Compose, pytest.

## Integration constraints

The Strava MCP connection used by interactive AI clients (for example Claude Code) is that client's own authorization transport. It cannot be handed to Django or Docker. Automation therefore uses your own Strava OAuth app, plus, optionally, your own Anthropic or OpenAI API key.

- `RUNTWIN_PROVIDER=strava_api` uses a dedicated Strava refresh token and safely persists rotated tokens.
- The webhook endpoint only validates, de-duplicates, and enqueues events behind a high-entropy path token. The separate `webhook-worker` does all external API calls.
- If the LLM is unavailable or not configured, the deterministic analysis is published instead. Strava or database failures are kept as failed events for retry and diagnosis.
- Snapshot mode works offline. Nothing scrapes AI web UIs or reuses interactive-tool logins.

See [`docs/mcp-capability-report.md`](docs/mcp-capability-report.md) and [`docs/sharing-and-deployment.md`](docs/sharing-and-deployment.md) (both in Chinese).

## Snapshot format

```json
{
  "schema_version": "runtwin-mcp-snapshot-v1",
  "activities": [{"id": "...", "name": "...", "start_local": "...", "sport_type": "Run", "summary": {}}],
  "streams": {
    "activity-id": {
      "time": [], "distance": [], "heart_rate": [], "velocity_smooth": [],
      "altitude": [], "grade_smooth": [], "cadence": [], "moving": [], "location": []
    }
  }
}
```

Snapshots, GPS, and private data are git-ignored. The repository only ships a fully synthetic fixture with no GPS.

## Docker

```bash
cp .env.example .env
# Set DJANGO_SECRET_KEY and POSTGRES_PASSWORD in .env; Compose refuses to start without them
docker compose up --build
```

Compose keeps rotated Strava tokens and exports in the `runtime_data` named volume. Back up that volume, and never bake tokens into an image or commit them.

The first start runs migrations and creates an empty, editable AthleteProfile. **No demo data is loaded automatically.** To create a login:

```bash
docker compose exec web env RUNTWIN_ADMIN_USERNAME=runner RUNTWIN_ADMIN_PASSWORD='change-me-long-random' python manage.py create_local_user
```

Then open <http://localhost:8000/weekly>. `seed_athlete_profile` only creates a profile when none exists, so restarts never overwrite your edits.

### Build a full weekly report from the anonymous fixture

```bash
docker compose exec web python manage.py import_mcp_snapshot fixtures/anonymous_mcp_snapshot.json
docker compose exec web python manage.py generate_weekly_report --week 2026-08-24 --export-prompt
```

## Local development

```bash
python -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_athlete_profile
python manage.py import_mcp_snapshot fixtures/anonymous_mcp_snapshot.json
python manage.py generate_weekly_report --week 2026-08-24 --export-prompt
python manage.py runserver
```

Without `DATABASE_URL`, RunTwin uses SQLite. Docker uses PostgreSQL.

## Management commands

```bash
python manage.py sync_strava_activities
python manage.py import_mcp_snapshot snapshots/private-export.json
python manage.py generate_weekly_facts [--week YYYY-MM-DD]
python manage.py generate_weekly_report [--week YYYY-MM-DD] [--export-prompt]
python manage.py regenerate_weekly_report --week YYYY-MM-DD [--export-prompt]
python manage.py import_ai_report output.json --week YYYY-MM-DD [--model-name ...]
python manage.py publish_activity_analysis <activity-id> --dry-run
python manage.py publish_activity_analysis <activity-id> --yes
python manage.py manage_strava_webhook list|create|delete [--subscription-id ID]
python manage.py process_strava_webhooks [--once] [--limit 20]
python manage.py reconcile_strava_activities [--days 14] [--limit 100]
python manage.py backfill_activity_analyses --since YYYY-MM-DD [--until YYYY-MM-DD] [--limit N] [--retry-fallback] [--batch-size 30] [--batch-pause-seconds 900] [--dry-run]
python manage.py generate_progress_narrative
python manage.py run_weekly_scheduler [--once]
```

`--week` must be a Monday. Without it, the report covers the last complete Asia/Taipei week, from Monday 00:00 (inclusive) to the next Monday 00:00 (exclusive).

`publish_activity_analysis` needs `activity:read,activity:write` on your Strava OAuth app (`activity:read_all` for Only Me activities). Preview with `--dry-run` first, then confirm with `--yes`. Your original description is preserved, and RunTwin maintains exactly one analysis block in it. The block marker comes from `RUNTWIN_ANALYSIS_LABEL` (default `RunTwin analysis`). If you change the label, list the old one in `RUNTWIN_LEGACY_ANALYSIS_LABELS` so old blocks get replaced.

### Analyze and publish every new run automatically

1. Create a personal Strava API application with at least `activity:read_all,activity:write`, and put the client ID, client secret, and refresh token in `.env`. `scripts/configure_strava_oauth.py` can do the OAuth exchange for you.
2. (Optional) Set `RUNTWIN_AI_PROVIDER=anthropic` with `ANTHROPIC_API_KEY`, or `RUNTWIN_AI_PROVIDER=openai` with `OPENAI_API_KEY`. See [AI modes](#ai-modes).
3. (Optional, real-time) Webhook setup:
   - Set a random `STRAVA_WEBHOOK_PATH_TOKEN` (at least 32 bytes) and a separate random `STRAVA_WEBHOOK_VERIFY_TOKEN`.
   - The public HTTPS `STRAVA_WEBHOOK_CALLBACK_URL` must end in `/webhooks/strava/<STRAVA_WEBHOOK_PATH_TOKEN>`, and its hostname must be in `DJANGO_ALLOWED_HOSTS`.
   - Run `python manage.py manage_strava_webhook create`, then `list`. Put the subscription ID in `STRAVA_WEBHOOK_SUBSCRIPTION_ID`, and your athlete ID in `STRAVA_ATHLETE_ID`.
   - Strava does not yet offer a usable signing secret, so `STRAVA_WEBHOOK_REQUIRE_SIGNATURE=0` by default.
4. Start the web app and the worker: `docker compose up --build`. For each run, the worker:
   - fetches the activity and its streams,
   - classifies the workout,
   - prefixes the title with an idempotent `[Type]` tag,
   - publishes a short zh-TW analysis with six sections: activity read, overall rating, data observations, training stimulus, recovery, and next 1–2 weeks based on 6–12 weeks of history.
5. Even without a webhook, the worker re-scans the last `STRAVA_RECONCILE_DAYS` (default 14) days every hour, which catches runs missed during downtime. After a longer outage, run `reconcile_strava_activities --days N`.
6. To inspect status, use `StravaWebhookEvent` in Django admin, or run `python manage.py process_strava_webhooks --once`.

Failed events are retried up to `STRAVA_WEBHOOK_MAX_ATTEMPTS` times. Events stuck longer than `STRAVA_WEBHOOK_PROCESSING_TIMEOUT_SECONDS` are re-queued. Activities and webhook deliveries are idempotent, so Strava retries and the `update` webhooks caused by RunTwin's own description edits never trigger a second analysis.

### Garmin supplementary metrics (optional)

Strava stays the primary source. Garmin only adds metrics that Strava lacks: training effect, training load, HR zones, running dynamics, Body Battery, VO2max, and weather. These are stored in `Activity.garmin_metrics` and passed to the LLM. Workout classification never changes because of Garmin data.

- **Unofficial API.** RunTwin uses the `garminconnect` package, which is not an official Garmin API and may break when Garmin changes.
- **Tokens.** Run `garmin-mcp-auth` in your own terminal (MFA required). Tokens default to `~/.garminconnect`. RunTwin never stores your Garmin password.
- **Enable** with `RUNTWIN_GARMIN_ENABLED=1`, and set `RUNTWIN_GARMIN_TOKEN_DIR` if needed. **Disable** with `RUNTWIN_GARMIN_ENABLED=0`, which is the default.
- **Failures** (login, lookup, or no match within ±120 s start time and ≤5% distance) only log a warning. Analysis and publishing still complete, with `garmin_metrics` left as `{}`.

To backfill history, preview with `backfill_activity_analyses --since 2025-06-01 --dry-run`, then run it again without `--dry-run`. Already-published runs are skipped, so the command is safe to re-run.

The dashboard's **progress factors** panel is recomputed on every load, using up to 78 complete weeks. It runs Spearman lagged correlations between the previous week's volume, frequency, long runs, quality sessions, easy share, and HR drift, and the next week's Easy/Long pace-to-HR efficiency. It needs at least 8 complete weeks and 6 outcome weeks. The results are personal historical associations, not causation and not race predictions. The daily scheduler asks the configured LLM for a plain-language summary, cached by input fingerprint; without an LLM, a deterministic summary is shown.

## AI modes

### 1. Deterministic fallback (default, always works)

`generate_weekly_report` builds a rule-based report. It is still validated against a Pydantic schema and activity-ID evidence, and works without any LLM API key.

### 2. Prompt export (semi-manual)

```bash
python manage.py generate_weekly_report --week 2026-08-24 --export-prompt
```

This writes `runtime/exports/<week>/weekly_facts.json` and `runtime/exports/<week>/weekly_analysis_prompt.md`. Give the prompt to any LLM, save the pure-JSON reply, then import it:

```bash
python manage.py import_ai_report response.json --week 2026-08-24 --model-name manual-llm
```

Imports that fail the schema or cite unknown activity IDs are rejected.

### 3. LLM API (Anthropic or OpenAI)

Per-activity analysis and the progress-factor summary can use an LLM. Only the two official APIs are supported, through their official Python SDKs. Use your own API key.

| Provider | `.env` | Default model | How it is called |
|---|---|---|---|
| Anthropic | `RUNTWIN_AI_PROVIDER=anthropic`, `ANTHROPIC_API_KEY=sk-ant-...` | `claude-opus-5-5` | `anthropic` SDK Messages API with adaptive thinking, `output_config.effort`, and server-side refusal fallback |
| OpenAI | `RUNTWIN_AI_PROVIDER=openai`, `OPENAI_API_KEY=sk-...` | `gpt-6.2-astra` | `openai` SDK Responses API with `reasoning.effort` and `store=False` |

- `RUNTWIN_AI_MODEL` overrides the model (for example `claude-sonnet-5-5` or `gpt-6.2-sol`). `RUNTWIN_AI_EFFORT` sets `low`, `medium`, or `high`.
- Leave `RUNTWIN_AI_PROVIDER` empty to disable the LLM. Refusals, truncated output, and malformed output all fall back to the deterministic analysis.
- The LLM only receives curated JSON facts: activity summary metrics, Garmin metrics, 12-week history, AthleteProfile goals, and the activity description. It never receives GPS coordinates or raw streams.
- Weekly `WeeklyReport`s are still deterministic or prompt-export only.

The implementation lives in `runtwin/ai/client.py`. A new provider only needs `generate_text(system=..., user=..., max_output_tokens=...)`.

## Scheduling

The Compose `scheduler` service refreshes the current week's report every day at 09:00 Asia/Taipei, and on Mondays it also finalizes the previous week. It catches up on startup. You can use an external cron instead:

```cron
CRON_TZ=Asia/Taipei
0 9 * * * cd /path/to/RunTwin && docker compose exec -T web python manage.py run_weekly_scheduler --once
```

In snapshot mode, the scheduler only analyzes data that has already been imported.

## URLs

- `/weekly`: latest weekly report
- `/weekly/history`: report history
- `/weekly/<week_start>`: a single week
- `/check-in`: weekly wellbeing check-in
- `/activities/<id>`: classification, stream features, and quality (no GPS)
- `/api/weekly`, `/api/weekly/<week_start>`, `/api/activities/<id>`: read-only DRF JSON (login required)

Everything except `/healthz` and the login page requires authentication. For HTTPS deployments, set `DJANGO_SECURE_COOKIES=1`, `DJANGO_SECURE_SSL_REDIRECT=1`, and a suitable `DJANGO_SECURE_HSTS_SECONDS`.

## Metrics and confidence

Every WeeklyFacts metric carries `value`, `unit`, `sample_size`, `coverage`, `confidence`, `calculation_version`, and `status`. When data is missing, `status` is `insufficient_data` rather than a guess. Activity names and descriptions only assist classification, and Tempo also requires stream evidence. HR drift is only computed for steady runs of at least 30 minutes with valid HR.

## Tests

```bash
pytest
```

The tests cover Taipei week boundaries, upserts, missing or abnormal HR, long pauses, 4-week averages, HR drift, classification, WeeklyFacts/AI schemas, AI evidence IDs, the Anthropic and OpenAI providers, report idempotency, and empty states. They never call Strava, Garmin, or any LLM.

## Security

- Data providers are read-only. Only `publish_activity_analysis` (with `activity:write` and `--yes`) and the worker modify Strava activities.
- Secrets live only in `.env`, which is git-ignored. Logs never print tokens.
- Snapshots, raw GPS, and private activity data are never committed.
- The dashboard never shows GPS routes.
- The fixture contains no real activity IDs, places, or coordinates.
- Pain input lives only in the weekly `WellbeingCheckIn` and is never stored on the AthleteProfile.

## Known limitations

- Single runner per deployment. See `docs/sharing-and-deployment.md` for what multi-user support would require.
- The Strava MCP cannot legally be called from a non-interactive backend, so full automation needs your own Strava OAuth app.
- Weekly reports do not use the LLM yet.
- ECharts loads from a CDN. Vendor it as a static asset for offline use.
- Rule-based classification and HR drift are proxies, not physiological measurements or medical advice.

## License

[MIT](LICENSE)
