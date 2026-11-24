from __future__ import annotations

from typing import Any

from .base import ReportProvider

CLASS_LABELS = {
    "easy": "輕鬆跑",
    "recovery": "恢復跑",
    "long": "長跑",
    "tempo_threshold": "節奏／閾值",
    "tempo": "節奏跑",
    "threshold": "閾值跑",
    "fartlek": "法特雷克",
    "interval": "間歇",
    "progression": "漸速跑",
    "race": "比賽",
    "unknown": "未知",
}


def evidence(metric_name: str, value: Any, activity: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "metric_name": metric_name,
        "metric_value": value,
        "activity_id": activity.get("activity_id") if activity else None,
        "date": activity.get("date") if activity else None,
        "activity_name": activity.get("name") if activity else None,
    }


def insight(claim: str, evidence_items: list[dict[str, Any]], confidence: str, reasoning: str) -> dict[str, Any]:
    ids = [item["activity_id"] for item in evidence_items if item.get("activity_id")]
    return {"claim": claim, "evidence": evidence_items, "confidence": confidence, "reasoning": reasoning, "related_activity_ids": ids}


class DeterministicFallbackProvider(ReportProvider):
    name = "deterministic-fallback-v1"

    def generate(self, facts: dict[str, Any]) -> dict[str, Any]:
        metrics = facts["metrics"]
        comparisons = facts["comparisons"]
        activities = facts["activity_facts"]
        wellbeing = facts.get("wellbeing")
        distance = metrics["total_distance"]["value"] or 0
        runs = metrics["run_count"]["value"] or 0
        elevation = metrics["total_elevation_gain"]["value"] or 0
        quality_count = metrics["quality_session_count"]["value"] or 0
        four_week_delta = comparisons["distance_vs_four_week_average"]
        longest = max(activities, key=lambda item: item["distance_km"], default=None)
        quality_activities = [
            item
            for item in activities
            if item["workout_class"] in {"tempo_threshold", "tempo", "threshold", "fartlek", "interval", "progression", "race"}
        ]
        positives: list[dict[str, Any]] = []
        concerns: list[dict[str, Any]] = []
        goal_gap: list[dict[str, Any]] = []

        if activities:
            positives.append(insight(
                f"本週完成 {runs} 次跑步，共 {distance:.1f} km。",
                [evidence("total_distance", distance), evidence("run_count", runs)],
                "high",
                "活動數與距離由已匯入活動直接加總。",
            ))
        if longest:
            positives.append(insight(
                f"最長跑為 {longest['distance_km']:.1f} km。",
                [evidence("distance_km", longest["distance_km"], longest)],
                "high",
                "以本週跑步活動距離排序取得。",
            ))
        if quality_activities:
            item = max(quality_activities, key=lambda activity: activity["moving_minutes"])
            positives.append(insight(
                f"本週包含 {quality_count} 次規則判定的品質課。",
                [evidence("quality_session_count", quality_count), evidence("workout_class", item["workout_class"], item)],
                "medium",
                "分類同時使用活動文字與 stream 特徵；仍屬推論而非人工標記。",
            ))

        quality_issues = facts["quality"]["issues"]
        if quality_issues:
            first = quality_issues[0]
            matching = next((item for item in activities if item["activity_id"] == first["activity_id"]), None)
            concerns.append(insight(
                f"本週有 {len(quality_issues)} 項資料品質提醒。",
                [evidence("quality_issues", matching["quality_issues"], matching)],
                "high",
                "資料缺漏或停等可能降低配速、心率與分類解讀可信度。",
            ))
        if four_week_delta["status"] == "ok" and abs(four_week_delta["value"]) >= 25:
            concerns.append(insight(
                f"跑量相較前四個完整週平均變化 {four_week_delta['value']:+.1f}%。",
                [evidence("distance_vs_four_week_average", four_week_delta["value"])],
                "medium",
                "單週偏離僅代表負荷變化，不能單獨證明適應或過度訓練。",
            ))
        if wellbeing and (wellbeing["knee_pain"] >= 4 or wellbeing["fatigue"] >= 7 or wellbeing["soreness"] >= 7):
            concerns.append(insight(
                "主觀疼痛或疲勞偏高，下一週應先降載。",
                [evidence("wellbeing", {key: wellbeing[key] for key in ("fatigue", "soreness", "knee_pain")})],
                "high",
                "主觀狀態超過保守安全門檻；這不是醫療診斷。",
            ))

        long_count = facts["workout_distribution"]["long"]["value"]
        threshold_count = sum(
            facts["workout_distribution"][key]["value"]
            for key in ("tempo_threshold", "tempo", "threshold")
        )
        if not long_count:
            goal_gap.append(insight("本週未辨識到長跑，長跑耐久代理指標不足。", [evidence("long_session_count", 0)], "medium", "Phase 1 僅使用長跑頻率作為耐久代理，不推算比賽成績。"))
        if not threshold_count and not quality_activities:
            goal_gap.append(insight("本週未辨識到閾值或其他品質刺激。", [evidence("quality_session_count", quality_count)], "medium", "分類依規則與 stream 特徵，活動若缺 stream 可能被列為未知。"))
        if not activities:
            concerns.append(insight("本週沒有可分析的跑步活動。", [evidence("run_count", 0)], "high", "無活動時不能推論能力變化或訓練缺口。"))

        high_recovery_risk = bool(wellbeing and (wellbeing["knee_pain"] >= 4 or wellbeing["fatigue"] >= 7 or wellbeing["soreness"] >= 7))
        if high_recovery_risk:
            priority = "恢復"
        elif not long_count:
            priority = "長跑耐久"
        elif quality_count == 0:
            priority = "閾值"
        elif four_week_delta["status"] == "ok" and four_week_delta["value"] > 25:
            priority = "維持與吸收"
        else:
            priority = "有氧量"

        sessions = self._sessions(priority, facts)
        limitations = ["Phase 1 不估算 LT1、LT2，也不預測比賽成績。"]
        if metrics["average_hr"]["status"] != "ok":
            limitations.append("心率覆蓋不足，無法可靠解讀整週平均心率。")
        if metrics["steady_run_hr_drift"]["status"] != "ok":
            limitations.append("沒有足夠且穩定的長時間 stream，無法計算心率漂移。")
        unknown = facts["workout_distribution"]["unknown"]["value"]
        if unknown:
            limitations.append(f"有 {unknown} 次活動因證據不足而分類為未知。")

        return {
            "executive_summary": f"本週完成 {runs} 次、{distance:.1f} km、爬升 {elevation:.0f} m。下週唯一首要目標為「{priority}」；所有判斷均由已匯入活動與確定性指標產生。" if activities else "本週沒有可分析的跑步活動，因此不判斷能力變化；先確認資料同步或保留恢復週紀錄。",
            "weekly_snapshot": [
                f"跑量：{distance:.1f} km",
                f"移動時間：{metrics['total_moving_time']['value'] or 0:.0f} 分鐘",
                f"爬升：{elevation:.0f} m",
                f"品質課：{quality_count} 次",
                f"相較四週平均：{four_week_delta['value']:+.1f}%" if four_week_delta["status"] == "ok" else "四週平均：資料不足",
            ],
            "positives": positives[:3],
            "concerns": concerns[:3],
            "goal_gap": goal_gap,
            "next_week_priority": priority,
            "suggested_sessions": sessions,
            "recovery_note": "若膝部疼痛、疲勞或痠痛升高，停止會誘發疼痛的跑步、改低衝擊活動，並尋求合格醫療或運動專業評估。" if high_recovery_risk else "品質課之間至少保留 48 小時；若疼痛出現或加劇，停止誘發疼痛的活動並尋求專業評估。",
            "data_limitations": limitations,
        }

    def _sessions(self, priority: str, facts: dict[str, Any]) -> list[dict[str, str]]:
        evidence_text = f"依據 {facts['week_start']} 至 {facts['week_end']} WeeklyFacts；首要方向為{priority}。"
        sessions = [
            {"day": "週二", "purpose": "有氧維持", "warmup": "10 分鐘非常輕鬆", "main_set": "40–50 分鐘 Easy，維持完整句子談話測試", "cooldown": "5–10 分鐘放鬆", "intensity": "RPE 2–3/10", "evidence": evidence_text, "fallback": "疲勞或疼痛時改休息或 30 分鐘低衝擊活動。"},
            {"day": "週三", "purpose": "主要品質刺激", "warmup": "15 分鐘 Easy＋4 次 20 秒加速", "main_set": "3×8 分鐘穩定偏快，組間慢跑 3 分鐘", "cooldown": "10–15 分鐘 Easy", "intensity": "RPE 6–7/10；可說短句，不追固定心率或配速", "evidence": evidence_text, "fallback": "疲勞偏高改 45 分鐘 Easy；疼痛則停止。"},
            {"day": "週五", "purpose": "恢復與跑姿", "warmup": "5–10 分鐘非常輕鬆", "main_set": "35–45 分鐘 Easy；狀態正常可加 4×20 秒放鬆加速", "cooldown": "5 分鐘走跑", "intensity": "RPE 2–3/10", "evidence": evidence_text, "fallback": "睡眠差或疼痛時取消加速跑。"},
            {"day": "週日", "purpose": "週末長跑耐久", "warmup": "前 15 分鐘刻意放慢", "main_set": "80–100 分鐘輕鬆長跑，時間依本週最長跑漸進，不增加品質強度", "cooldown": "5–10 分鐘走跑與補水", "intensity": "RPE 3–4/10，以談話測試為主", "evidence": evidence_text, "fallback": "疼痛、疲勞 ≥7 或痠痛 ≥7 時縮短 30–50%，必要時停止。"},
        ]
        if priority == "恢復":
            sessions[1] = {"day": "週三", "purpose": "恢復", "warmup": "5 分鐘走路", "main_set": "30–40 分鐘非常輕鬆跑或低衝擊交叉訓練", "cooldown": "5 分鐘走路", "intensity": "RPE 1–2/10", "evidence": evidence_text, "fallback": "任何疼痛加劇立即停止並尋求專業評估。"}
            sessions[3]["main_set"] = "60–75 分鐘輕鬆跑，不加速"
        return sessions
