# Strava MCP Capability Report

檢查日期：2026-09-03（Asia/Taipei）

## 結論

Claude Code 的 Strava MCP 已連線，帳戶具有完整 MCP 工具集。它是 Claude 客戶端使用的遠端 HTTP MCP（`https://mcp.strava.com/mcp`），而不是 RunTwin Web Backend 可持有或重用的 OAuth/API credential。CLI 設定沒有暴露可供 Django、cron 或 Docker scheduler 合法呼叫的 token，也沒有已驗證的 headless 授權流程。

因此 Phase 1 判定：

- **互動式 Claude 工作階段可唯讀取得資料。**
- **非互動式 Django／排程不可假設能直接呼叫。**
- 不爬取 AI 客戶端畫面、不複製任何登入狀態、不將任何 credential 放入程式。
- RunTwin 使用 `StravaDataProvider` 邊界；除 snapshot JSON adapter 外，現在也已實作獨立 Strava OAuth API adapter。互動式 MCP 仍不能當作 backend credential。

## 可用工具、主要參數與回傳欄位

| MCP tool | 主要參數 | 主要回傳欄位 |
|---|---|---|
| `eligibility` | 無 | `eligible`, `message` |
| `list_activities` | `first`, `after`, `ordering`, `range_start`, `range_end`, `include_polyline`, `include_tags` | activity `id`, `name`, `description`, `sport_type`, `start_local`, `location_summary`, `gear_id`; summary `distance`, `moving_time`, `elapsed_time`, `elevation_gain`, `avg_speed`, `max_speed`, `avg_cadence`, `calories`, `relative_effort`; paging cursor |
| `get_activity_performance` | `activity_id` | HR/power availability、平均／最高心率、功率、步頻、calories、PR、segments、best efforts、laps（距離、時間、爬升、HR、功率、步頻、grade、speed） |
| `get_activity_streams` | `activity_id`, `streams[]`, optional `resolution` | requested arrays；支援 `time`, `distance`, `heart_rate`, `watts`, `cadence`, `location`, `altitude`, `velocity_smooth`, `grade_smooth`, `moving`, `temp` |
| `get_athlete_profile` | 無 | athlete profile、單位、體重、位置、current focus |
| `get_athlete_zones` | optional `as_of_date` | HR/power/run zones 與來源、estimated flags |
| `get_gear` | optional `gear_types` | bikes/shoes 與距離 |
| `get_strength_workout_details` | `activity_ids[]` | sets、exercise、muscle groups、weight/reps/duration |
| `get_club_info` | paging args | clubs、events |
| `get_training_plan` | 無 | 可用訓練計畫資訊 |

## 最小唯讀能力驗證

已確認互動式 MCP 可取得 Activity list、activity performance/details，以及 time、distance、heart rate、velocity、altitude、grade、cadence、moving status 與 GPS streams。本文件不保存任何實際跑者的活動時間、距離、心率、座標或識別碼。完整精度可省略 `resolution`，但輸出量大；snapshot 匯出時應保存足夠解析度並一律視為私人資料。

## 自動化狀態

| 能力 | 狀態 |
|---|---|
| Fixture 匯入→分析→Dashboard | 已自動化 |
| MCP snapshot 匯入 | 已自動化，但 snapshot 需由已授權互動式工作階段產生 |
| 每週 facts/report 產生 | 已自動化；scheduler 每日 09:00 更新當週，週一同時結算上一週 |
| 互動式 Strava MCP 自動同步 | **未自動化**；不支援 headless backend credential |
| Strava 官方 API OAuth adapter | 已實作單一跑者的 refresh token 同步、Webhook、補抓與回填；尚無多人 OAuth onboarding |
| LLM API | 單次活動與進步摘要支援官方 Anthropic 或 OpenAI API；未設定時使用 deterministic fallback；週報仍為 fallback／PromptExport |
