# RunTwin

[English](README.md) | **繁體中文**

自架式 Strava 跑步分析工具。RunTwin 透過你自己的 Strava OAuth 應用同步跑步紀錄，用規則判定每堂課的類型，計算每週指標（跑量、長跑、品質課、心率漂移、配速心率效率），並可把簡短的教練分析寫回每筆活動的 description。LLM 是選配：可接 **Anthropic（Claude）** 或 **OpenAI**（使用你自己的 API key），也可以完全不用 AI。

> 要在自己的 Windows 電腦部署並連接自己的 Strava，請閱讀 [`DISTRIBUTION-SOP.zh-TW.md`](DISTRIBUTION-SOP.zh-TW.md)。本 repository 不含任何個人帳號、活動、token、API key 或資料庫。

**快速體驗（不需要 Strava 帳號）：**

```bash
python -m venv .venv && . .venv/bin/activate   # Windows：.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate && python manage.py seed_athlete_profile
python manage.py import_mcp_snapshot fixtures/anonymous_mcp_snapshot.json
python manage.py generate_weekly_report --week 2026-08-24
RUNTWIN_ADMIN_USERNAME=runner RUNTWIN_ADMIN_PASSWORD='請改成長隨機密碼' python manage.py create_local_user
python manage.py runserver           # 開啟 http://localhost:8000/weekly
```

RunTwin 是個人化、可追溯證據的跑步週分析 Web App。Phase 1 以 deterministic Python analytics 計算所有數字，AI 只解釋乾淨的 `WeeklyFacts`，不直接讀取巨大原始 streams，也不估算 LT1／LT2 或比賽成績。

## Phase 1 能力

- Strava-compatible provider boundary；可匯入 MCP snapshot，也可用獨立 OAuth 應用同步 Strava API。
- Activity/stream 正規化、upsert 去重、資料品質評分。
- 規則＋stream features 的活動分類，保留信心、理由與版本。
- Asia/Taipei 完整週期、前週／四週平均／六週趨勢。
- 距離、時間、爬升、長跑、品質課、HR/pace coverage、穩定跑 HR drift、pace-to-HR efficiency。
- 固定 schema 的繁中週報、活動 evidence、主觀狀態與 responsive Dashboard。
- deterministic fallback report；可匯出 prompt 給任一 LLM，再驗證匯入 JSON；或設定 Anthropic／OpenAI API 自動產生單次活動分析。
- PostgreSQL、Docker Compose、pytest。

## 重要整合限制

互動式 AI 客戶端（例如 Claude Code）連線的 Strava MCP 只是該客戶端的授權 transport，不能把它的憑證交給 Django／Docker。自動化模式必須使用你自己建立並授權的 Strava OAuth 應用，以及（選配的）你自己的 Anthropic 或 OpenAI API key：

- `RUNTWIN_PROVIDER=strava_api` 使用獨立 Strava OAuth refresh token，同步時會安全保存旋轉後的新 token。
- `webhook-worker` 只處理由含高熵 path token 的 webhook callback 快速入列的新活動事件；不在 HTTP callback 內呼叫外部 API。
- 若 LLM 暫時失敗或未設定，仍會用 deterministic 分析回填；Strava／資料庫等流程錯誤則保留失敗紀錄供重試與診斷。
- Snapshot 模式仍可離線使用；不爬任何 AI 網頁，也不重用互動式工具的登入資訊。

詳見 [`docs/mcp-capability-report.md`](docs/mcp-capability-report.md)。若要交付他人、自行部署或規劃多人服務，請先閱讀 [`docs/sharing-and-deployment.md`](docs/sharing-and-deployment.md)（中文）。

## Snapshot 格式

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

Snapshot、GPS 與私人資料均已列入 `.gitignore`；repository 只有完全合成、無 GPS 的匿名 fixture。

## Docker 啟動

```bash
cp .env.example .env
# Compose 會要求 .env 設定 DJANGO_SECRET_KEY 與 POSTGRES_PASSWORD，未設定時拒絕啟動
docker compose up --build
```

Compose 使用 `runtime_data` named volume 保存旋轉後的 Strava token 與匯出檔，避免 Linux bind mount 權限讓 refresh token 無法寫入。若要備份，請備份該 Docker volume，不要把 token 放進 image 或版控。從舊版 `./runtime` bind mount 升級時，需將既有 `strava-token.json` 安全複製進 named volume，或以 `STRAVA_REFRESH_TOKEN` 重新初始化。

首次啟動會 migration、建立可修改的 AthleteProfile，**不會自動顯示假資料**。建立登入帳號：

```bash
docker compose exec web env RUNTWIN_ADMIN_USERNAME=runner RUNTWIN_ADMIN_PASSWORD='請改成長隨機密碼' python manage.py create_local_user
```

接著開啟 <http://localhost:8000/weekly>，系統會要求登入。`seed_athlete_profile` 僅在尚無 profile 時建立資料，不會於容器重啟時覆寫使用者修改。

### 用匿名 fixture 建立完整週報

```bash
docker compose exec web python manage.py import_mcp_snapshot fixtures/anonymous_mcp_snapshot.json
docker compose exec web python manage.py generate_weekly_report --week 2026-08-24 --export-prompt
```

## 本機開發

```bash
python -m venv .venv
. .venv/bin/activate            # Windows：.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_athlete_profile
python manage.py import_mcp_snapshot fixtures/anonymous_mcp_snapshot.json
python manage.py generate_weekly_report --week 2026-08-24 --export-prompt
python manage.py runserver
```

未設定 `DATABASE_URL` 時使用 SQLite 方便開發與測試；Docker 使用 PostgreSQL。

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
python manage.py run_weekly_scheduler [--once]
```

`--week` 必須是星期一。不傳時，報告範圍為 Asia/Taipei 的上一個完整週一 00:00（含）至下一週一 00:00（不含），畫面顯示至週日。

`publish_activity_analysis` 使用獨立 Strava OAuth 應用的 `activity:read,activity:write` 權限。先設定 `STRAVA_CLIENT_ID`、`STRAVA_CLIENT_SECRET`、`STRAVA_REFRESH_TOKEN`；建議先用 `--dry-run` 預覽，確認後再加 `--yes` 寫入。程式會保留原 description，並更新單一分析區塊（標記文字由 `RUNTWIN_ANALYSIS_LABEL` 設定，預設 `RunTwin analysis`）而不重複附加；若改過標記，把舊標記列入 `RUNTWIN_LEGACY_ANALYSIS_LABELS` 即可在更新時替換舊區塊。Only Me 活動另需 `activity:read_all`。

### 自動分析並回填每次新跑步

1. 連接 Strava：建立自己的 Strava API application（callback domain 填 `localhost`），再執行 `python scripts/configure_strava_oauth.py`。它會開啟 Strava 授權頁、確認 `activity:read_all` 與 `activity:write` 都有授權，並把 client ID、secret、refresh token 與 athlete ID 寫入 `.env`。逐欄說明見 [DISTRIBUTION-SOP.zh-TW.md 第 4 節](DISTRIBUTION-SOP.zh-TW.md#4-連接-strava)。
2. （選配）設定 `RUNTWIN_AI_PROVIDER=anthropic` 加 `ANTHROPIC_API_KEY`，或 `RUNTWIN_AI_PROVIDER=openai` 加 `OPENAI_API_KEY`，詳見下方「AI 模式」。另設定至少 32 bytes 的隨機 `STRAVA_WEBHOOK_PATH_TOKEN` 與另一組隨機 `STRAVA_WEBHOOK_VERIFY_TOKEN`。公開 HTTPS `STRAVA_WEBHOOK_CALLBACK_URL` 必須以 `/webhooks/strava/<STRAVA_WEBHOOK_PATH_TOKEN>` 結尾，且該公開 hostname 必須列入 `DJANGO_ALLOWED_HOSTS`。截至 2026-09，Strava 尚未正式提供可用的 webhook signing secret，因此預設 `STRAVA_WEBHOOK_REQUIRE_SIGNATURE=0`；日後正式開放時再填 secret 並啟用驗證。
3. 確認上述公開 callback 可連線，執行 `python manage.py manage_strava_webhook create`；再用 `list` 取得 subscription ID，填入必要的 `STRAVA_WEBHOOK_SUBSCRIPTION_ID`。個人部署也必須填 `STRAVA_ATHLETE_ID`，worker 會在讀取或寫入活動前驗證兩者；完整活動仍透過你的 OAuth token 從 Strava 重新取得。
4. 啟動 Web 與 worker：`docker compose up --build`。Webhook endpoint 只驗證、去重並入列，會在兩秒內回覆；`webhook-worker` 另行讀取 activity/streams、判定 Easy／Recovery／Long／Tempo／Threshold／Intervals／Fartlek／Progression／Race，以冪等 `[Type]` 前綴更新 title，並產生含少量 emoji 的繁中分析（活動判讀、整體評比、數據觀察、這堂課練了什麼、恢復與下一步、依 6–12 週歷史的下一步）。原 title 與 description 會保留，分析區塊只會有一份。Worker 每小時也會掃描近 `STRAVA_RECONCILE_DAYS`（預設 14）天活動，補上停機或 webhook 遺漏期間的新跑步；電腦或 Docker 停機超過此天數時，請手動執行 `reconcile_strava_activities --days N`。
5. 檢查狀態：Django admin 的 `StravaWebhookEvent`，或本機執行 `python manage.py process_strava_webhooks --once`。

LLM 暫時不可用或未設定時，worker 使用 deterministic 分析完成回填；Strava 或資料庫等流程錯誤則保留為 failed，最多自動嘗試 `STRAVA_WEBHOOK_MAX_ATTEMPTS` 次。若 worker 中途終止，超過 `STRAVA_WEBHOOK_PROCESSING_TIMEOUT_SECONDS` 的事件會重新排入。活動與 webhook delivery 皆具冪等鍵，Strava 重送事件或 description 更新產生的 `update` webhook 不會重複分析。

### Garmin 補充資料（選用）

Strava 仍是主要來源；Garmin 只補充 Strava 沒有的指標（訓練效果、訓練負荷、心率區間、跑姿、Body Battery、VO2max 與天氣），存在 `Activity.garmin_metrics` 並交給 LLM 分析。活動分類仍由 RunTwin 規則決定，不會因 Garmin 訓練效果改變 title 的 `[Type]`。

- **非官方 API**：使用 `garminconnect` 套件存取 Garmin Connect，不是 Garmin 官方開放的 API，可能因 Garmin 改版而失效。
- **連線**：在自己的終端機執行一次 `python scripts/configure_garmin_auth.py`。它會詢問 Garmin email、密碼與 MFA 驗證碼，把 token 存到 `~/.garminconnect`，並在 `.env` 設定 `RUNTWIN_GARMIN_ENABLED=1`。RunTwin 不保存 Garmin 密碼；之後 Garmin 要求重新登入（token 過期或被撤銷）時，重新執行即可。完整步驟見 [DISTRIBUTION-SOP.zh-TW.md 第 7 節](DISTRIBUTION-SOP.zh-TW.md#7-連接-garmin選配)。
- **自訂位置**：要把 token 放在其他資料夾，執行腳本時加 `--token-dir`。
- **關閉**：設定 `RUNTWIN_GARMIN_ENABLED=0`（預設）。
- **失敗處理**：登入、查詢失敗或找不到配對（開始時間 ±120 秒、距離差 ≤ 5%）時只記錄 warning，分析與回填照常完成，`garmin_metrics` 保持 `{}`。同一次 backfill／reconcile 共用一個 Garmin 連線。

所有活動與週報使用 `update_or_create`；同週重跑不重複新增。歷史補分析先用 `backfill_activity_analyses --since 2025-06-01 --dry-run` 預覽，再移除 `--dry-run` 執行；指令會略過已發布項目，失敗後可安全重跑。

Dashboard 的「進步關鍵因素」會在每次載入時，使用最近最多 78 個完整週重新計算。模型以 Easy／Long 跑的配速心率效率作為觀察結果，將前一週跑量、頻率、長跑、品質課、Easy 占比與心率漂移和下一週效率做 Spearman 時序關聯；至少 8 個完整週且 6 個有效結果週才顯示。此結果是個人歷史關聯，不是因果推論或比賽成績預測。每日 scheduler 會將通過門檻的統計 JSON 交給設定的 LLM 產生白話摘要，並以 fingerprint 快取；模型輸入改變時才重新生成，LLM 失敗或未設定則顯示 deterministic 摘要。也可手動執行 `python manage.py generate_progress_narrative`。

## AI 模式

### 1. Deterministic fallback（預設，可完全執行）

`generate_weekly_report` 由規則產生繁中報告，仍會經 Pydantic schema 與 activity ID evidence 驗證。這不是生成式 AI，但可在沒有任何 LLM API key 時完整運作。

### 2. PromptExport（半自動）

```bash
python manage.py generate_weekly_report --week 2026-08-24 --export-prompt
```

輸出：

- `runtime/exports/<week>/weekly_facts.json`
- `runtime/exports/<week>/weekly_analysis_prompt.md`

將 prompt 交給任一 LLM，保存純 JSON 回應後：

```bash
python manage.py import_ai_report response.json --week 2026-08-24 --model-name manual-llm
```

匯入會拒絕 schema 不符或引用不存在 activity ID 的內容。**此模式不是完全自動化。**

### 3. LLM API（Anthropic 或 OpenAI）

單次活動分析與「進步關鍵因素」白話摘要可交給 LLM。只支援兩家官方 API，並使用官方 Python SDK；請使用你自己申請的 API key，不要沿用任何公司或互動式工具的憑證。

| Provider | `.env` 設定 | 預設模型 | 呼叫方式 |
|---|---|---|---|
| Anthropic | `RUNTWIN_AI_PROVIDER=anthropic`、`ANTHROPIC_API_KEY=sk-ant-...` | `claude-opus-5-5` | `anthropic` SDK Messages API，adaptive thinking、`output_config.effort`，以及 server-side refusal fallback |
| OpenAI | `RUNTWIN_AI_PROVIDER=openai`、`OPENAI_API_KEY=sk-...` | `gpt-6.2-astra` | `openai` SDK Responses API，`reasoning.effort`，`store=False` |

- `RUNTWIN_AI_MODEL` 可覆寫模型（例如 `claude-sonnet-5-5`、`gpt-6.2-sol`），`RUNTWIN_AI_EFFORT` 設定 `low`／`medium`／`high`。
- `RUNTWIN_AI_PROVIDER` 留空即停用 LLM。拒答、輸出被截斷或格式不完整時，都會自動改用 deterministic 分析。
- 送給 LLM 的只有整理過的 JSON facts（活動摘要數據、Garmin 指標、12 週歷史、AthleteProfile 目標與活動 description），不會送出 GPS 座標或原始 streams。
- 每週 `WeeklyReport` 仍是 deterministic fallback 或 PromptExport，尚未接 LLM。

實作位於 `runtwin/ai/client.py`。新增 provider 只要實作 `generate_text(system=..., user=..., max_output_tokens=...)`。

## 排程

Compose 內含 `scheduler`，每日 09:00 Asia/Taipei 更新進行中的當週 fallback report 並匯出 prompt；週一會同時結算上一完整週。Scheduler 啟動時也會補算當週與上一週。也可使用每日外部 cron：

```cron
CRON_TZ=Asia/Taipei
0 9 * * * cd /path/to/RunTwin && docker compose exec -T web python manage.py run_weekly_scheduler --once
```

注意：snapshot 模式只會分析已匯入資料；排程本身不會從互動式 MCP 取得新活動。

## URL

- `/weekly`：最新週報
- `/weekly/history`：歷史週報
- `/weekly/<week_start>`：單週詳細報告
- `/check-in`：本週主觀狀態
- `/activities/<id>`：分類、stream features、品質結果（不顯示 GPS）
- `/api/weekly`、`/api/weekly/<week_start>`、`/api/activities/<id>`：需登入的唯讀 DRF JSON

除 `/healthz` 與 Django 登入頁外，個人訓練頁面與 API 均要求登入。正式 HTTPS 部署時請設定 `DJANGO_SECURE_COOKIES=1`、`DJANGO_SECURE_SSL_REDIRECT=1` 與適當的 `DJANGO_SECURE_HSTS_SECONDS`。

## 分析與信心

每個 WeeklyFacts metric 含：

- `value`
- `unit`
- `sample_size`
- `coverage`
- `confidence`
- `calculation_version`
- `status`

資料不足時是 `insufficient_data`，不是猜測。分類文字只作輔助；Tempo 必須同時有 stream 證據。HR drift 只分析至少 30 分鐘、速度變異在門檻內且具有效 HR 的穩定跑。Phase 1 的 goal gap 僅使用週量穩定、品質／閾值刺激頻率、長跑代理、Easy/Quality 平衡與恢復狀態。

## 測試

```bash
pytest
```

目前涵蓋：Taipei 週界與跨月／年、upsert、缺 HR、HR 異常、長停等、四週平均、HR drift、分類、WeeklyFacts/AI schemas、AI evidence ID、Anthropic／OpenAI provider、週報冪等與 empty state。測試不會連線到 Strava、Garmin 或任何 LLM。

## 安全

- 資料匯入 providers 維持唯讀；只有 `publish_activity_analysis` 在提供獨立 Strava OAuth `activity:write` 且加上 `--yes` 時才會修改指定活動 description。
- secrets 只可放 `.env`（已列入 `.gitignore`）；日誌不輸出 token。
- snapshot、原始 GPS、私人 activity data 不入版控。
- Dashboard 不公開 GPS 路線。
- 匿名 fixture 不含真實活動 ID、地點或座標。
- 疼痛輸入只存在每週 `WellbeingCheckIn`，不會永久寫入 AthleteProfile。

## 已知限制

- Strava MCP 尚不能由非互動式 backend／scheduler 合法直接呼叫；全自動化需獨立 Strava OAuth app。
- 單次活動與進步摘要已接 LLM；每週週報尚未接 LLM。
- ECharts 從 CDN 載入；離線環境可改成 vendored static asset。
- 規則分類與 HR drift 是 Phase 1 proxy，不能視為生理量測或醫療判斷。

## License

[MIT](LICENSE)
