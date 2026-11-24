from __future__ import annotations

import re

from runtwin.activities.models import Activity

TITLE_PREFIX_PATTERN = re.compile(r"^\[(?:Easy|Recovery|Long|Tempo(?:/Threshold)?|Threshold|Intervals|Fartlek|Progression|Race|Run)\]\s*")
TITLE_LABELS = {
    "easy": "Easy",
    "recovery": "Recovery",
    "long": "Long",
    "tempo": "Tempo",
    "threshold": "Threshold",
    "tempo_threshold": "Tempo/Threshold",
    "interval": "Intervals",
    "fartlek": "Fartlek",
    "progression": "Progression",
    "race": "Race",
    "unknown": "Run",
}


def strip_run_type_prefix(name: str) -> str:
    value = (name or "").strip()
    while TITLE_PREFIX_PATTERN.match(value):
        value = TITLE_PREFIX_PATTERN.sub("", value, count=1).strip()
    return value


def classified_activity_title(activity: Activity, current_name: str | None = None) -> str:
    original = strip_run_type_prefix(current_name if current_name is not None else activity.name)
    label = TITLE_LABELS.get(activity.workout_class, "Run")
    prefix = f"[{label}] "
    return f"{prefix}{(original or 'Run')[: 255 - len(prefix)]}"
