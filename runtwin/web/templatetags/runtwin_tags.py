from django import template

register = template.Library()


@register.filter
def get_item(mapping, key):
    if isinstance(mapping, dict):
        return mapping.get(key)
    return None


@register.filter
def pace(value):
    if value in (None, ""):
        return "—"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "—"
    minutes = int(numeric // 60)
    seconds = int(round(numeric % 60))
    if seconds == 60:
        minutes += 1
        seconds = 0
    return f"{minutes}:{seconds:02d}/km"


@register.filter
def km(value):
    if value is None:
        return "—"
    return f"{float(value) / 1000:.2f}"


@register.filter
def duration(value):
    if value is None:
        return "—"
    total = int(value)
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


@register.filter
def confidence_label(value):
    return {"high": "高信心", "medium": "中信心", "low": "低信心"}.get(str(value), "未評估")


@register.filter
def confidence_percent(value):
    if value is None:
        return "—"
    return f"{float(value) * 100:.0f}%"


@register.filter
def workout_label(value):
    labels = {
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
        "unknown": "待判定",
    }
    return labels.get(str(value), str(value))


@register.filter
def signed_percent(value):
    if value in (None, ""):
        return "—"
    try:
        return f"{float(value):+.1f}%"
    except (TypeError, ValueError):
        return "—"


@register.filter
def as_percent(value):
    if value in (None, ""):
        return "—"
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "—"


@register.filter
def ratio_percent(value):
    if value in (None, ""):
        return "—"
    try:
        return f"{(float(value) - 1) * 100:+.1f}%"
    except (TypeError, ValueError):
        return "—"
