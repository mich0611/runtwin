# RunTwin 個人自架版：安裝與使用 SOP

[English](DISTRIBUTION-SOP.md) | **繁體中文**

這份文件供「每位跑者在自己的 Windows 電腦上啟動一套 RunTwin，連接自己的 Strava 帳號」使用。Repository 不含任何人的帳號、活動、資料庫、token、API key 或訓練目標。

## 0. 先了解需求

> 隱私提醒：回填後，Strava 活動 description 會出現 RunTwin 分析區塊（標記由 `RUNTWIN_ANALYSIS_LABEL` 設定）。若不希望第三方看到，請在 Strava 將活動設為 Only Me，或不要執行回填命令。

### 必要

- Windows 10／11
- Python 3.11 或 3.12
- Git（`git clone` 本 repository），或從 GitHub 下載 ZIP
- Strava 帳號
- 若要自動讀取 Strava：由你自己的 Strava 帳號建立 API Application

依 Strava 目前規則，建立 API Application 的帳號需要 Strava 訂閱。若不使用 Strava API，仍可用匿名 fixture 或自行準備的 snapshot 測試。

### 選配

- Anthropic 或 OpenAI API key：用 LLM 產生較完整的單次活動分析；沒有也能使用規則式 fallback。
- Docker Desktop：若想使用 PostgreSQL 與容器常駐服務。第一次使用建議先依本文的「Windows 本機模式」。
- Garmin Connect 帳號：若你也用 Garmin 手錶記錄跑步（第 7 節）。
- 公開 HTTPS 網域／Tunnel：只有即時 Webhook 需要；不設定也能由 worker 每小時補抓。

## 1. 取得原始碼

```powershell
git clone https://github.com/<你的帳號>/runtwin.git C:\RunTwin
```

或下載 ZIP，解壓到不含特殊權限限制的路徑，例如 `C:\RunTwin`。

以下 PowerShell 指令都在該目錄執行：

```powershell
Set-Location C:\RunTwin
```

## 2. 建立 Python 環境

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

若沒有 Python 3.12，可使用 Python 3.11：

```powershell
py -3.11 -m venv .venv
```

## 3. 建立自己的 `.env`

```powershell
Copy-Item .env.example .env
```

產生 Django secret：

```powershell
.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(64))"
```

編輯 `.env`，本機模式至少設定：

```dotenv
DJANGO_SECRET_KEY=貼上剛才產生的值
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000
DATABASE_URL=
RUNTWIN_PROVIDER=strava_api
RUNTWIN_EXPORT_DIR=runtime/exports

RUNTWIN_ADMIN_USERNAME=runner
RUNTWIN_ADMIN_PASSWORD=請改成自己的長隨機密碼
RUNTWIN_ADMIN_EMAIL=
```

`.env` 含密碼和 token，不能上傳、傳給別人或提交至版本控制。

## 4. 連接 Strava

RunTwin 透過**你自己的** Strava API Application 存取 Strava：先建立一次，再授權它存取你的帳號。

### 4.1 建立 API Application

1. 用瀏覽器登入 Strava，開啟 <https://www.strava.com/settings/api>。
2. 填寫表單：
   | 欄位 | 填寫內容 |
   |---|---|
   | Application Name | 任意名稱，例如 `My RunTwin` |
   | Category | `Training`（任何類別都可以） |
   | Website | 任意網址，例如 `http://localhost` |
   | Authorization Callback Domain | `localhost`（只填這個字，不要加 `http://` 或 port） |
3. 若 Strava 要求上傳圖示，任意圖片即可，並同意 API 條款。
4. 在 App 頁面複製 **Client ID**（數字）與 **Client Secret**（按 *show* 顯示）。Secret 要當成密碼保管。

### 4.2 授權你的帳號

在 RunTwin 資料夾執行內附工具：

```powershell
.venv\Scripts\python.exe scripts\configure_strava_oauth.py
```

1. 依提示貼上 Client ID 與 Client Secret。
2. 瀏覽器會開啟 Strava 授權頁。**兩個權限勾選框都要保持勾選**，再按 **Authorize**：
   - *View data about your private activities*（`activity:read_all`）：讀取所有跑步，包含 Only Me 活動。
   - *Upload your activities … to Strava*（`activity:write`）：寫入 `[Easy]`／`[Long]` 標題與分析區塊。
3. 瀏覽器顯示 *"Strava authorization received. You can close this window."*
4. 終端機顯示 `Updated .env with this athlete's Strava OAuth settings.`

工具會等待 5 分鐘，完成後寫入 `.env`：

```dotenv
STRAVA_CLIENT_ID=你的Client ID
STRAVA_CLIENT_SECRET=你的Client Secret
STRAVA_REFRESH_TOKEN=你的Refresh Token
STRAVA_ATHLETE_ID=你的數字Athlete ID
```

之後 RunTwin 會自動更新 access token，並把旋轉後的 token 存到 `STRAVA_TOKEN_FILE`。除非你撤銷授權，否則不需要重做。

### 4.3 確認連線

```powershell
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py sync_strava_activities
```

沒有錯誤並顯示匯入的活動數量，就代表 Strava 已連上。

### 4.4 常見問題

| 症狀 | 解法 |
|---|---|
| Strava 頁面顯示 `redirect_uri invalid` | Authorization Callback Domain 必須剛好是 `localhost`。 |
| `Authorization is missing required permissions` | 有權限被取消勾選。重新執行工具，兩個都保持勾選。 |
| `Timed out waiting for the Strava redirect` | 重新執行，並在 5 分鐘內完成授權。 |
| 瀏覽器打不開 `localhost:8765` | 8765 port 被佔用或被防火牆擋住，改用 `--redirect-uri http://localhost:8766/callback`。 |
| 沒有瀏覽器（伺服器、SSH） | 加 `--no-browser`，在任何已登入 Strava 的裝置開啟印出的網址，再把最後跳轉的 `localhost` 網址拿到 RunTwin 這台電腦開啟；或依 Strava 官方 OAuth 文件手動取得：<https://developers.strava.com/docs/authentication/>。 |
| `sync_strava_activities` 回傳 `401` | Client secret 錯誤或授權已撤銷，重新執行工具。 |

之後若要中斷連線，到 <https://www.strava.com/settings/apps> 撤銷 RunTwin 的授權。

## 5. 設定 AI 分析（選配）

二選一，使用你自己申請的 API key。

Anthropic（Claude），key 從 <https://console.anthropic.com/> 取得：

```dotenv
RUNTWIN_AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-你的金鑰
RUNTWIN_AI_MODEL=
```

OpenAI，key 從 <https://platform.openai.com/api-keys> 取得：

```dotenv
RUNTWIN_AI_PROVIDER=openai
OPENAI_API_KEY=sk-你的金鑰
RUNTWIN_AI_MODEL=
```

`RUNTWIN_AI_MODEL` 留空時使用預設模型（Anthropic `claude-opus-5-5`，OpenAI `gpt-6.2-astra`）。想降低費用可改成 `claude-sonnet-5-5` 或 `gpt-6.2-sol`。

不使用 AI 時把 `RUNTWIN_AI_PROVIDER` 留空，系統會使用 deterministic fallback。

## 6. 初始化資料庫與帳號

```powershell
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py seed_athlete_profile
.venv\Scripts\python.exe manage.py create_local_user
```

`seed_athlete_profile` 只建立不含個人資訊的空白 profile。

啟動後登入 Django Admin：

<http://127.0.0.1:8000/admin/>

進入 **Athlete profiles**，填入自己的：

- 時區
- 半馬 PB／目標
- 全馬目標
- 一般週跑量
- 每週跑步次數
- 平日單次距離上限
- 長跑日
- 暫定節奏心率
- 已觀察最高心率

不要直接沿用別人的數值。資料不足的欄位可先留空；一般週跑量與平日距離上限若未知可先填 `0`。

## 7. 連接 Garmin（選配）

Strava 仍是主要資料來源。若你也用 Garmin 手錶記錄跑步，RunTwin 可以在每次分析加入 Strava 沒有的 Garmin 指標：訓練效果、訓練負荷、心率區間、跑姿、Body Battery、VO2max 與天氣。不接 Garmin 也能完整使用。

> Garmin Connect 沒有提供給個人專案的官方 API。RunTwin 使用非官方的 `garminconnect` 套件，Garmin 改版登入流程時可能失效。Garmin 出錯不會影響 Strava 分析。

### 7.1 登入一次

```powershell
.venv\Scripts\python.exe scripts\configure_garmin_auth.py
```

1. 輸入 Garmin Connect 的 email 和密碼。密碼只用這一次，不會被儲存。
2. 帳號有開兩步驟驗證的話，在 `Garmin MFA code:` 提示輸入 Garmin 寄給你的驗證碼。
3. 終端機顯示 `Garmin tokens saved to ...` 和 `Updated .env: RUNTWIN_GARMIN_ENABLED=1 ...` 就完成了。

Token 會存在 `~/.garminconnect`（Windows 是 `C:\Users\<你的使用者>\.garminconnect`）。這個資料夾等同 Garmin 帳號的存取權，請勿外流或提交到版本控制。常用選項：`--token-dir <資料夾>` 改存放位置、`--is-cn` 用於 Garmin 中國區帳號、`--no-env` 不修改 `.env`。

### 7.2 配對方式

每一筆 Strava 跑步，RunTwin 會找開始時間相差 ±120 秒內、距離差 5% 以內的 Garmin 跑步活動。配對到的指標存在 `Activity.garmin_metrics` 並交給分析使用；沒配對到的跑步就沒有 Garmin 資料。

### 7.3 確認連線

首次同步（第 8 節）後，打開一筆最近的跑步 `http://127.0.0.1:8000/activities/<id>`。有配對到時，分析內容會提到 Garmin 訓練效果或心率區間。Garmin 的問題只會在 worker 輸出中以 warning 出現，例如 `Garmin metrics unavailable`。

### 7.4 Docker

Worker 與 scheduler 會掛載主機上的 `RUNTWIN_GARMIN_HOST_TOKEN_DIR`（預設 `~/.garminconnect`）。先在主機執行上面的腳本，再於 `.env` 設定 `RUNTWIN_GARMIN_ENABLED=1` 並重啟 Compose。

### 7.5 常見問題

| 症狀 | 解法 |
|---|---|
| 執行腳本時顯示 `Garmin login failed` | 確認 email 和密碼。先用瀏覽器登入 <https://connect.garmin.com> 一次，處理掉可能的安全確認，再重試。 |
| Worker 出現 `Garmin metrics unavailable` | Token 過期或被撤銷，重新執行 `configure_garmin_auth.py`。 |
| 某筆跑步沒有 Garmin 資料 | 這趟沒有用 Garmin 記錄，或開始時間、距離和 Strava 那筆差太多。 |
| 想關閉 Garmin | 設定 `RUNTWIN_GARMIN_ENABLED=0` 並重啟，可刪除 token 資料夾。 |

## 8. 首次同步與測試

同步自己的 Strava 活動：

```powershell
.venv\Scripts\python.exe manage.py sync_strava_activities
```

立即掃描最近 14 天、分析尚未發布的跑步並回填 Strava：

```powershell
.venv\Scripts\python.exe manage.py reconcile_strava_activities --days 14 --limit 100
```

注意：`reconcile_strava_activities` 會修改 Strava 活動的標題與 description。可先用指定 activity ID 預覽既有本機分析：

```powershell
.venv\Scripts\python.exe manage.py publish_activity_analysis <activity-id> --dry-run
```

## 9. 啟動三個常駐程序

開三個 PowerShell 視窗，全部進入 `C:\RunTwin`。

### 視窗 A：Web

```powershell
.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --noreload
```

開啟：

<http://127.0.0.1:8000/weekly>

### 視窗 B：新活動 Worker

```powershell
.venv\Scripts\python.exe manage.py process_strava_webhooks
```

即使沒有公開 Webhook，worker 預設仍會每小時掃描最近 14 天（`STRAVA_RECONCILE_DAYS`），補抓新活動。停機超過這個天數時，請手動執行 `reconcile_strava_activities --days N`。

### 視窗 C：每日週報 Scheduler

```powershell
.venv\Scripts\python.exe manage.py run_weekly_scheduler
```

它會每日 09:00（Asia/Taipei）更新當週週報，週一同時結算上一週。

關閉任一視窗就會停止相應服務。若需要開機自動啟動，建議改用 Docker Compose 或自行建立 Windows Scheduled Task／service。

## 10. Webhook 即時模式（進階、選配）

沒有 Webhook 時最慢約等待一個 reconciliation interval。若希望上傳 Strava 後立即處理，需要：

1. 一個固定的公開 HTTPS URL。
2. 兩組獨立的隨機 token：

```powershell
.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

3. 在 `.env` 設定：

```dotenv
STRAVA_WEBHOOK_PATH_TOKEN=第一組隨機值
STRAVA_WEBHOOK_VERIFY_TOKEN=第二組隨機值
STRAVA_WEBHOOK_CALLBACK_URL=https://你的網域/webhooks/strava/第一組隨機值
STRAVA_WEBHOOK_SUBSCRIPTION_ID=
```

4. 確認公開 health endpoint 可連線。
5. 建立 subscription：

```powershell
.venv\Scripts\python.exe manage.py manage_strava_webhook create
```

6. 將回傳的 ID 填入：

```dotenv
STRAVA_WEBHOOK_SUBSCRIPTION_ID=回傳的數字
```

7. 重新啟動 Web 與 worker。

## 11. Docker 模式（選配）

1. 安裝並啟動 Docker Desktop。
2. `.env` 裡的路徑使用容器預設值，例如：

```dotenv
DATABASE_URL=postgresql://runtwin:你的資料庫密碼@db:5432/runtwin
RUNTWIN_EXPORT_DIR=/app/runtime/exports
STRAVA_TOKEN_FILE=/app/runtime/strava-token.json
POSTGRES_PASSWORD=你的資料庫密碼
DJANGO_SECRET_KEY=長隨機字串
```

Compose 在 `POSTGRES_PASSWORD` 或 `DJANGO_SECRET_KEY` 未設定時會拒絕啟動。

3. 啟動：

```powershell
docker compose up --build -d
docker compose ps
```

4. 建立登入帳號：

```powershell
docker compose exec web python manage.py create_local_user
```

Compose 會啟動 PostgreSQL、Web、worker 與每日 scheduler。公開 Webhook 仍需額外的 HTTPS reverse proxy 或 tunnel。

## 12. 驗證與故障排除

Django 設定：

```powershell
.venv\Scripts\python.exe manage.py check
```

Web 健康狀態：

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/healthz
```

預期：

```json
{"status":"ok"}
```

執行測試（不會連線到 Strava、Garmin 或任何 LLM）：

```powershell
.venv\Scripts\python.exe -m pytest
```

常見問題：

- LLM `401`：`ANTHROPIC_API_KEY`／`OPENAI_API_KEY` 錯誤或與 `RUNTWIN_AI_PROVIDER` 不符；活動會降級為 fallback。
- Strava `401`：refresh token、client ID／secret 不正確，或 token 已撤銷。
- 無法回填：OAuth 缺少 `activity:write`。
- Only Me 活動抓不到：OAuth 缺少 `activity:read_all`。
- 新活動沒有立刻出現：確認 worker 持續運作，或手動執行 reconciliation。
- `.env` 修改後未生效：重新啟動 Web、worker 與 scheduler。
- SQLite `database is locked`：避免重複啟動多份 worker／server；長期部署改用 Docker PostgreSQL。

## 13. 安全檢查

分享、備份或回報問題前，絕對不要附上：

- `.env`
- `db.sqlite3`
- `runtime/strava-token.json`
- `runtime/` logs／exports
- `snapshots/`
- 畫面截圖中的個人資料
- Garmin token 資料夾（`~/.garminconnect`）
- Client secret、refresh token、Anthropic／OpenAI key

更完整的部署與多人架構說明請閱讀 [`docs/sharing-and-deployment.md`](docs/sharing-and-deployment.md)。
