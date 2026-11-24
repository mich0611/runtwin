from __future__ import annotations

from typing import Any

from runtwin.activities.models import Activity
from runtwin.classification.title import classified_activity_title

from django.conf import settings

# The marker wraps RunTwin's block inside the Strava description so re-publishing replaces it
# instead of appending. Changing RUNTWIN_ANALYSIS_LABEL later leaves old blocks in place unless
# the old label is listed in RUNTWIN_LEGACY_ANALYSIS_LABELS.
ANALYSIS_LABEL = settings.RUNTWIN_ANALYSIS_LABEL
ANALYSIS_START = f"--- {ANALYSIS_LABEL} ---"
ANALYSIS_END = f"--- /{ANALYSIS_LABEL} ---"
LEGACY_ANALYSIS_BLOCKS = tuple(
    (f"--- {label} ---", f"--- /{label} ---")
    for label in ("RunTwin 分析", *settings.RUNTWIN_LEGACY_ANALYSIS_LABELS)
    if label and label != ANALYSIS_LABEL
)


def strip_analysis_from_description(description: str) -> str:
    value = description or ""
    for start_marker, end_marker in ((ANALYSIS_START, ANALYSIS_END), *LEGACY_ANALYSIS_BLOCKS):
        while True:
            start = value.find(start_marker)
            end = value.find(end_marker, start + len(start_marker)) if start >= 0 else -1
            if start < 0 or end < 0:
                break
            end += len(end_marker)
            value = f"{value[:start].rstrip()}\n\n{value[end:].lstrip()}"
    return value.strip()


def merge_analysis_into_description(description: str, analysis: str) -> str:
    description = description or ""
    analysis = analysis.strip()
    if not analysis:
        raise ValueError("活動尚無分析內容。")

    block = f"{ANALYSIS_START}\n{analysis}\n{ANALYSIS_END}"
    user_description = strip_analysis_from_description(description)
    return f"{user_description.rstrip()}\n\n{block}".strip()


def publish_activity_analysis(
    activity: Activity,
    client: Any,
    *,
    dry_run: bool = False,
    remote: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not activity.analysis.strip():
        raise ValueError("活動尚無分析內容。")
    remote = remote or client.get_activity(activity.strava_activity_id)
    remote_id = str(remote.get("id", ""))
    if remote_id != activity.strava_activity_id:
        raise ValueError("Strava 回傳的 activity ID 與本機紀錄不一致。")

    original_name = remote.get("name") or activity.name
    original_description = remote.get("description") or ""
    name = classified_activity_title(activity, original_name)
    description = merge_analysis_into_description(original_description, activity.analysis)
    if dry_run:
        return {
            "activity_id": activity.strava_activity_id,
            "name": name,
            "description": description,
            "updated": False,
        }
    if name == original_name and description == original_description:
        return {
            "activity_id": activity.strava_activity_id,
            "name": name,
            "description": description,
            "updated": False,
            "remote": remote,
        }
    updated = client.update_activity(activity.strava_activity_id, name=name, description=description)
    activity.name = name
    activity.save(update_fields=["name"])
    return {
        "activity_id": activity.strava_activity_id,
        "name": name,
        "description": description,
        "updated": True,
        "remote": updated,
    }
