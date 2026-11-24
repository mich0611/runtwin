# 將 RunTwin 提供給其他人使用

RunTwin 目前是**單一跑者、自行部署**的應用，不是已完成資料隔離的多人 SaaS。請依使用方式選擇部署模式。

## 是否需要 Strava 訂閱

依 [Strava Getting Started](https://developers.strava.com/docs/getting-started/) 目前規則，**建立 Strava API Application 的開發者必須有 Strava 訂閱**。這與一般使用者授權是兩件事：

- 建立／持有 API Application 的人：需要符合 Strava 的訂閱與開發者要求。
- 使用既有應用程式的跑者：需要 Strava 帳號並透過 OAuth 個別授權；不需要取得或接觸 client secret。
- 完全離線使用匿名 fixture 或匯入 snapshot：不需要 Strava 帳號、訂閱或 API Application。

新 Strava Application 預設是 single-player mode，只能讓擁有者本人連線。依官方文件完成設定後可在 API Dashboard 申請／調整至最多 10 位 connected athletes；超過容量需送 Strava app review，且仍受 rate limit 與 API Agreement 約束。

## Strava 不是一把 API key

自動同步需要 OAuth 2.0：

- 服務方保存一組 `STRAVA_CLIENT_ID` 與 `STRAVA_CLIENT_SECRET`。
- 每位跑者在 Strava 授權後，各自取得 access token 與 refresh token。
- Access token 約六小時到期；refresh 時可能旋轉 refresh token，必須保存最新值。
- 讀取私人活動需要 `activity:read_all`。
- 修改活動標題或 description 需要 `activity:write`。

詳見 [Strava OAuth Authentication](https://developers.strava.com/docs/authentication/)。

## LLM 是否必要

LLM 憑證是**選配**：

- Anthropic：`RUNTWIN_AI_PROVIDER=anthropic` 加 `ANTHROPIC_API_KEY`。
- OpenAI：`RUNTWIN_AI_PROVIDER=openai` 加 `OPENAI_API_KEY`。
- 未設定：單次活動使用 deterministic fallback；週報本來就是 deterministic fallback。

服務方通常集中持有 LLM API key，不應把金鑰交給跑者。

## 使用模式與需求

| 模式 | Strava | LLM | 適用情境 |
|---|---|---|---|
| 匿名 fixture | 不需要 | 不需要 | 展示與本機試用 |
| Snapshot 匯入 | 不需要 Strava API Application | 選配 | 手動、離線分析 |
| 自動輪詢 | OAuth client ID／secret＋跑者 refresh token | 選配 | 單人自架、不需公開網址 |
| Webhook 即時處理 | 上述 OAuth＋公開 HTTPS callback＋subscription | 選配 | 單人完整自動化 |
| 多人 SaaS | 一個通過容量／review 要求的服務方 App＋每人 OAuth token | 通常由服務方提供 | 需要先完成多租戶改造 |

除了服務整合憑證，正式部署還要設定 Django secret、資料庫密碼、管理員密碼、HTTPS hostname，以及 Webhook path／verify token。

## 現在要交給少數人：建議每人獨立部署

目前最安全且不需大改程式的方式是：

1. 每位跑者使用獨立 container、資料庫與 runtime volume。
2. 每套只建立一個本機登入帳號與 AthleteProfile。
3. 每套使用該跑者自己的 OAuth refresh token。
4. 若由你代管，Strava client secret 與 LLM API key 只留在伺服器，不交給跑者。
5. 若跑者在自己的電腦部署，建議他們建立自己的 Strava Application；不要散發你的 client secret。
6. 若不需要即時 Webhook，可只開 Web、worker 與每小時 reconciliation，不必提供公開 HTTPS endpoint。

## 為什麼目前不能直接共用一個網站給多人

目前資料模型與背景流程有單人假設：

- `AthleteProfile` 未綁定 Django user。
- `Activity`、stream 與 Webhook event 未綁定 athlete owner。
- 頁面和 API 只有登入檢查，沒有依使用者隔離 queryset。
- Strava refresh token、token file 與 athlete ID 是全域設定。
- Worker 只接受一個 `STRAVA_ATHLETE_ID`。
- 尚無「Connect with Strava」authorize／callback onboarding 流程。

因此，讓多位跑者登入同一套現有部署可能互相看到資料，**不可直接當多人服務上線**。

## 要做正式多人服務，需要的改造

1. 新增 user-owned `AthleteAccount` 與 Strava OAuth authorize／callback。
2. 加密保存每位跑者最新的 refresh token；client secret 僅由伺服器持有。
3. 將 Activity、ActivityStream、WeeklyReport、WellbeingCheckIn 與 Webhook event 全部綁定 athlete。
4. 所有頁面與 API 強制依登入 user 過濾。
5. Webhook 依 `owner_id` 選出 athlete 與對應 token。
6. 加入解除 Strava 連線、刪除帳號、資料匯出與保留政策。
7. 背景 queue 依 athlete 處理 rate limit、重試與冪等。
8. 準備隱私權政策、服務條款、Strava 品牌規範與 app review。
9. 監控 [Strava API rate limits](https://developers.strava.com/docs/rate-limits/)。

## 快速開始

匿名展示：

```powershell
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py seed_athlete_profile
.venv\Scripts\python.exe manage.py import_mcp_snapshot fixtures/anonymous_mcp_snapshot.json
.venv\Scripts\python.exe manage.py generate_weekly_report --week 2026-08-24
.venv\Scripts\python.exe manage.py runserver
```

單人 Strava 自動化的環境變數與命令請接續閱讀主 [`README.md`](../README.md#自動分析並回填每次新跑步)。
