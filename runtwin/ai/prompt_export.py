from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.conf import settings

from runtwin.reporting.schemas import AIReportSchema
from .base import ReportProvider

SYSTEM_RULES = """你是 RunTwin 跑步訓練分析助手。僅使用提供的 WeeklyFacts JSON，輸出台灣繁體中文 JSON，且必須符合指定 schema。數學與統計已由系統計算，不得自行重算或新增數字。清楚區分事實、推論與建議；不可將相關性寫成因果，不可將估算寫成生理實測，不作 LT1、LT2 或比賽成績預測。每個 positives、concerns、goal_gap 項目必須包含 claim、evidence、confidence、reasoning、related_activity_ids；活動 ID 只能引用 WeeklyFacts.activities 中存在的 ID。重要結論須附活動日期、名稱或 ID。資料不足就明說。不得醫療診斷。若疼痛偏高，降低強度並建議停止造成疼痛的活動及尋求專業評估。建議 4–5 次跑步、平日不超過 10–12 km、週末長跑、不連續兩天高強度，也不應同時大幅提高跑量與品質強度。next_week_priority 只能有一個主要方向。"""


class PromptExportProvider(ReportProvider):
    name = "prompt-export"

    def __init__(self, output_dir: str | Path | None = None):
        self.output_dir = Path(output_dir or settings.RUNTWIN_EXPORT_DIR)

    def generate(self, facts: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("PromptExportProvider 不會假裝呼叫 AI；請使用 export() 後手動匯入結果。")

    def export(self, facts: dict[str, Any]) -> tuple[Path, Path]:
        week = facts["week_start"]
        target = self.output_dir / week
        target.mkdir(parents=True, exist_ok=True)
        facts_path = target / "weekly_facts.json"
        prompt_path = target / "weekly_analysis_prompt.md"
        facts_path.write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding="utf-8")
        schema = AIReportSchema.model_json_schema()
        prompt = f"""# RunTwin 每週分析請求

{SYSTEM_RULES}

## 輸出 JSON Schema

```json
{json.dumps(schema, ensure_ascii=False, indent=2)}
```

## WeeklyFacts

```json
{json.dumps(facts, ensure_ascii=False, indent=2)}
```

請只輸出 JSON，不要 Markdown code fence。
"""
        prompt_path.write_text(prompt, encoding="utf-8")
        return facts_path, prompt_path
