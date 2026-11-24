from types import SimpleNamespace

import pytest

from runtwin.ai.progress import (
    REQUIRED_HEADINGS,
    SYSTEM_PROMPT,
    ProgressNarrator,
    context_lines,
    deterministic_progress_narrative,
    get_progress_narrative,
    progress_fingerprint,
)
from runtwin.reporting.models import ProgressNarrative

FULL_TEXT = "\n".join(f"{heading}\n內容。" for heading in REQUIRED_HEADINGS)


def context(**overrides):
    value = {
        "window_weeks": 12,
        "weeks_with_runs": 12,
        "sufficient_for_trend": True,
        "run_count": 60,
        "average_weekly_distance_km": 56.1,
        "recent_4_week_distance_km": 48.5,
        "long_run_count": 7,
        "workout_class_counts": {"easy": 40, "long": 7, "mystery": 1},
        "easy_efficiency_trend": {"sample_count": 27, "earlier_half_mean": 1.3, "later_half_mean": 1.33, "later_minus_earlier": 0.03},
        "steady_hr_drift_trend": {"sample_count": 3, "earlier_half_mean": None, "later_half_mean": 2.0, "later_minus_earlier": None},
        "garmin": {
            "weeks_with_data": 10,
            "matched_run_count": 27,
            "average_weekly_training_load": 412.5,
            "average_aerobic_training_effect": 3.4,
            "z1_z2_share_percent": None,
            "high_dew_point_runs": 9,
        },
    }
    value.update(overrides)
    return value


class FakeGenerator:
    name = "fake"
    model = "fake-model"

    def __init__(self, text):
        self.text = text
        self.calls = []

    def generate_text(self, **kwargs):
        self.calls.append(kwargs)
        return self.text


def progress():
    return {
        "model_version": "progress-association-v1",
        "status": "ok",
        "confidence": "medium",
        "complete_week_count": 70,
        "outcome_week_count": 11,
        "outcome_label": "效率",
        "factors": [{"label": "週跑量", "correlation": 0.648, "sample_size": 10, "confidence": "medium", "direction_text": "較高時較好", "recent_value": 54.39, "unit": "km／週", "source": "strava"}],
        "garmin_week_count": 10,
        "training_context": context(),
        "limitations": ["不代表因果"],
    }


def test_progress_narrator_uses_only_verified_model_payload():
    generator = FakeGenerator(FULL_TEXT)

    result = ProgressNarrator(generator).generate(progress())

    assert result == FULL_TEXT
    prompt = generator.calls[0]["user"]
    assert "0.648" in prompt
    assert "不代表因果" in prompt
    assert "412.5" in prompt
    assert '"garmin_week_count": 10' in prompt


@pytest.mark.parametrize("missing", REQUIRED_HEADINGS)
def test_progress_narrator_rejects_missing_heading(missing):
    text = "\n".join(f"{heading}\n內容。" for heading in REQUIRED_HEADINGS if heading != missing)

    with pytest.raises(RuntimeError, match="格式不完整"):
        ProgressNarrator(FakeGenerator(text)).generate(progress())


def test_progress_prompt_asks_for_five_context_points_and_garmin():
    assert all(heading in SYSTEM_PROMPT for heading in REQUIRED_HEADINGS)
    for phrase in ("週跑量", "各分類次數", "長跑次數", "Easy 跑效率趨勢", "穩定跑心率漂移趨勢", "training_context.garmin", "高露點"):
        assert phrase in SYSTEM_PROMPT


def test_progress_fingerprint_changes_with_garmin_context():
    changed = progress()
    changed["training_context"] = context(garmin={**context()["garmin"], "average_weekly_training_load": 999})

    assert progress_fingerprint(changed) != progress_fingerprint(progress())


def test_context_lines_cover_five_points_and_garmin():
    lines = context_lines(context())

    assert lines[0] == "- 週跑量：平均 56.1 km，近 4 週 48.5 km。"
    assert lines[1] == "- 分類次數：輕鬆跑 40、長跑 7、mystery 1。"
    assert lines[2] == "- 長跑：12 週共 7 次。"
    assert lines[3] == "- Easy 跑效率：前段 1.3 → 後段 1.33（n=27）。"
    assert lines[4] == "- 穩定跑心率漂移：樣本不足（n=3）。"
    assert lines[5] == "- Garmin（27 趟）：週訓練負荷 412.5、有氧 TE 3.4、Z1–Z2 占比 —%、高露點 9 次。"
    assert len(lines) == 6


def test_context_lines_without_garmin_and_sparse_history():
    lines = context_lines(context(
        sufficient_for_trend=False,
        workout_class_counts={},
        garmin={"matched_run_count": 0},
        easy_efficiency_trend={},
    ))

    assert lines[1] == "- 分類次數：無。"
    assert lines[3] == "- Easy 跑效率：樣本不足（n=0）。"
    assert lines[5] == "- Garmin：這段期間沒有可配對的 Garmin 資料。"
    assert lines[6] == "- 有跑步的週數不足 6 週，趨勢僅供參考。"


@pytest.mark.parametrize("value", [{}, {"window_weeks": 0}])
def test_context_lines_without_weeks(value):
    assert context_lines(value) == ["- 尚無足夠的完整週可整理訓練脈絡。"]


def test_context_lines_tolerates_missing_garmin_block():
    value = context()
    del value["garmin"]

    assert context_lines(value)[5] == "- Garmin：這段期間沒有可配對的 Garmin 資料。"


@pytest.mark.parametrize("factors", [[], None])
def test_deterministic_narrative_includes_context_with_and_without_factors(factors):
    value = progress()
    if factors is not None:
        value["factors"] = factors

    text = deterministic_progress_narrative(value)

    assert all(heading in text for heading in REQUIRED_HEADINGS)
    assert "週跑量：平均 56.1 km" in text
    assert "Garmin（27 趟）" in text
    if factors == []:
        assert "還沒有足夠穩定的個人關聯" in text
    else:
        assert "ρ=0.648" in text


def test_deterministic_narrative_without_context():
    text = deterministic_progress_narrative({"factors": []})

    assert "尚無足夠的完整週可整理訓練脈絡" in text


@pytest.mark.django_db
def test_progress_narrative_is_cached_by_fingerprint():
    item = ProgressNarrative.objects.create(
        fingerprint=progress_fingerprint(progress()),
        model_version="progress-association-v1",
        source="ai:fake",
        narrative="cached",
    )

    result = get_progress_narrative(progress(), generate=True, narrator=SimpleNamespace(generate=lambda _: (_ for _ in ()).throw(AssertionError())))

    assert result["text"] == "cached"
    assert result["generated_at"] == item.generated_at


@pytest.mark.django_db
def test_progress_narrative_falls_back_and_persists_on_ai_failure():
    narrator = SimpleNamespace(generate=lambda _: (_ for _ in ()).throw(RuntimeError("offline")))

    result = get_progress_narrative(progress(), generate=True, narrator=narrator)

    assert result["source"] == "deterministic-fallback"
    assert "相關性不等於因果" in result["text"]
    assert "近 12 週訓練脈絡" in result["text"]
    assert ProgressNarrative.objects.count() == 1


def test_progress_narrator_rejects_empty_text():
    with pytest.raises(RuntimeError, match="格式不完整"):
        ProgressNarrator(FakeGenerator("")).generate(progress())


@pytest.mark.django_db
def test_progress_narrative_without_generate_is_live_and_not_saved():
    result = get_progress_narrative(progress())

    assert result["source"] == "deterministic-live"
    assert "近 12 週訓練脈絡" in result["text"]
    assert ProgressNarrative.objects.count() == 0


@pytest.mark.django_db
def test_progress_narrative_saves_ai_text_with_provider_source():
    result = get_progress_narrative(progress(), generate=True, narrator=ProgressNarrator(FakeGenerator(FULL_TEXT)))

    assert result["source"] == "ai:fake"
    assert ProgressNarrative.objects.get().narrative == FULL_TEXT
