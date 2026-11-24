from types import SimpleNamespace

from runtwin.classification.title import classified_activity_title, strip_run_type_prefix


def activity(workout_class, name="Morning Run"):
    return SimpleNamespace(workout_class=workout_class, name=name)


def test_classified_title_uses_run_type_labels():
    assert classified_activity_title(activity("easy")) == "[Easy] Morning Run"
    assert classified_activity_title(activity("tempo")) == "[Tempo] Morning Run"
    assert classified_activity_title(activity("threshold")) == "[Threshold] Morning Run"
    assert classified_activity_title(activity("fartlek")) == "[Fartlek] Morning Run"
    assert classified_activity_title(activity("interval")) == "[Intervals] Morning Run"


def test_classified_title_replaces_existing_runtwin_prefix_idempotently():
    item = activity("threshold", "[Tempo] Morning Run")

    first = classified_activity_title(item)
    second = classified_activity_title(item, first)

    assert first == "[Threshold] Morning Run"
    assert second == first


def test_classified_title_never_exceeds_database_limit():
    result = classified_activity_title(activity("tempo", "X" * 255))

    assert len(result) == 255
    assert result.startswith("[Tempo] ")


def test_strip_run_type_prefix_preserves_user_title():
    assert strip_run_type_prefix("[Easy] Riverside with Friends") == "Riverside with Friends"
    assert strip_run_type_prefix("[Tempo/Threshold] [Easy] Riverside") == "Riverside"
    assert strip_run_type_prefix("Custom [Easy] Run") == "Custom [Easy] Run"
