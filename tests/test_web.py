from datetime import date, timedelta

import pytest
from django.urls import reverse

from runtwin.activities.models import Activity
from runtwin.athletes.models import AthleteProfile
from runtwin.reporting.models import WeeklyReport


@pytest.mark.django_db
def test_weekly_requires_authentication(client):
    response = client.get(reverse("weekly_latest"))
    assert response.status_code == 302
    assert "/admin/login/" in response.url


@pytest.mark.django_db
def test_empty_state_for_authenticated_user(client, django_user_model):
    user = django_user_model.objects.create_user(username="runner", password="secret")
    client.force_login(user)
    response = client.get(reverse("weekly_latest"))
    assert response.status_code == 200
    assert "尚無週報" in response.content.decode()


@pytest.mark.django_db
def test_weekly_report_displays_progress_model_section(client, django_user_model, athlete, monkeypatch):
    user = django_user_model.objects.create_user(username="runner", password="secret")
    client.force_login(user)
    week = date.today() - timedelta(days=date.today().weekday() + 7)
    WeeklyReport.objects.create(athlete=athlete, week_start=week, week_end=week + timedelta(days=6), facts_json={})
    monkeypatch.setattr("runtwin.web.views.build_progress_analysis", lambda: {
        "status": "ok",
        "confidence": "medium",
        "summary": "週跑量與下一週效率呈正向關聯。",
        "outcome_label": "效率",
        "complete_week_count": 12,
        "outcome_week_count": 10,
        "factors": [{
            "label": "週跑量", "strength": "moderate", "confidence": "medium",
            "direction_text": "較高時，下一週效率通常較好", "correlation": 0.4,
            "sample_size": 10, "recent_value": 55, "unit": "km／週", "source": "strava",
        }, {
            "label": "Garmin 週訓練負荷", "strength": "moderate", "confidence": "medium",
            "direction_text": "較高時，下一週效率通常較好", "correlation": 0.35,
            "sample_size": 10, "recent_value": 420, "unit": "load／週", "source": "garmin",
        }],
        "garmin_week_count": 10,
        "training_context": {
            "window_weeks": 12, "sufficient_for_trend": False, "run_count": 60,
            "average_weekly_distance_km": 56.1, "recent_4_week_distance_km": 48.5, "long_run_count": 7,
            "workout_class_counts": {"easy": 40, "long": 7},
            "easy_efficiency_trend": {"sample_count": 27, "earlier_half_mean": 1.3, "later_half_mean": 1.33, "later_minus_earlier": 0.03},
            "steady_hr_drift_trend": {"sample_count": 1, "earlier_half_mean": None, "later_half_mean": 2.0, "later_minus_earlier": None},
            "garmin": {"matched_run_count": 27, "average_weekly_training_load": 412.5, "average_aerobic_training_effect": 3.4, "z1_z2_share_percent": 61.2, "high_dew_point_runs": 9},
        },
        "limitations": ["不代表因果"],
        "model_version": "test-v1",
    })
    monkeypatch.setattr("runtwin.web.views.get_progress_narrative", lambda progress: {
        "text": "白話總結：穩定訓練是目前重點。",
        "source": "ai:anthropic",
        "generated_at": None,
    })

    response = client.get(reverse("weekly_latest"))

    content = response.content.decode()
    assert response.status_code == 200
    assert "進步關鍵因素" in content
    assert "週跑量與下一週效率呈正向關聯" in content
    assert "AI 白話解讀" in content
    assert "穩定訓練是目前重點" in content
    assert "不代表因果" in content
    assert "Garmin 資料週" in content
    assert "近 12 週訓練脈絡" in content
    assert "有跑步的週數不足 6 週" in content
    for label in ("① 週跑量", "② 各分類次數", "③ 長跑次數", "④ Easy 跑效率趨勢", "⑤ 穩定跑心率漂移趨勢"):
        assert label in content
    assert "平均 56.1 km／週" in content
    assert "輕鬆跑 40" in content
    assert "1.3 → 1.33" in content
    assert "週訓練負荷 412.5" in content
    assert "高露點 9 次" in content
    assert "Garmin 週訓練負荷" in content
    assert "factor-card--garmin" in content
    assert "Garmin · moderate" in content


@pytest.mark.django_db
def test_weekly_report_progress_section_without_garmin_or_context(client, django_user_model, athlete, monkeypatch):
    user = django_user_model.objects.create_user(username="runner", password="secret")
    client.force_login(user)
    week = date.today() - timedelta(days=date.today().weekday() + 7)
    WeeklyReport.objects.create(athlete=athlete, week_start=week, week_end=week + timedelta(days=6), facts_json={})
    base = {
        "status": "limited", "confidence": "low", "summary": "資料不足。", "outcome_label": "效率",
        "complete_week_count": 3, "outcome_week_count": 1, "factors": [], "limitations": [], "model_version": "test-v1",
    }
    monkeypatch.setattr("runtwin.web.views.get_progress_narrative", lambda progress: {"text": "x", "source": "deterministic-live", "generated_at": None})

    monkeypatch.setattr("runtwin.web.views.build_progress_analysis", lambda: dict(base))
    content = client.get(reverse("weekly_latest")).content.decode()
    assert "訓練脈絡" not in content

    context = {
        "window_weeks": 3, "sufficient_for_trend": True, "run_count": 3,
        "average_weekly_distance_km": 10.0, "recent_4_week_distance_km": 10.0, "long_run_count": 0,
        "workout_class_counts": {},
        "easy_efficiency_trend": {"sample_count": 0, "later_minus_earlier": None},
        "steady_hr_drift_trend": {"sample_count": 2, "earlier_half_mean": 5.0, "later_half_mean": 4.0, "later_minus_earlier": -1.0},
        "garmin": {"matched_run_count": 0, "high_dew_point_runs": 0},
    }
    monkeypatch.setattr("runtwin.web.views.build_progress_analysis", lambda: {**base, "training_context": context})
    content = client.get(reverse("weekly_latest")).content.decode()
    assert "近 3 週訓練脈絡" in content
    assert "有跑步的週數不足" not in content
    assert "<strong>無</strong>" in content
    assert "樣本不足" in content
    assert "5.0% → 4.0%" in content
    assert "沒有可配對的 Garmin 資料" in content
    assert "Garmin 資料週</dt><dd>0" in content


@pytest.mark.django_db
def test_history_page_exposes_reports_for_three_month_frontend_filter(client, django_user_model):
    user = django_user_model.objects.create_user(username="runner", password="secret")
    client.force_login(user)
    athlete = AthleteProfile.objects.create()
    recent = date.today() - timedelta(days=14)
    old = date.today() - timedelta(days=140)
    WeeklyReport.objects.create(athlete=athlete, week_start=recent, week_end=recent + timedelta(days=6))
    WeeklyReport.objects.create(athlete=athlete, week_start=old, week_end=old + timedelta(days=6))

    response = client.get(reverse("weekly_history"))
    content = response.content.decode()

    assert response.status_code == 200
    assert "近三個月週報" in content
    assert f'data-week-start="{recent.isoformat()}"' in content
    assert f'data-week-start="{old.isoformat()}"' in content
    assert "web/js/history.js" in content


@pytest.mark.django_db
def test_api_requires_authentication(client):
    response = client.get(reverse("api_weekly"))
    assert response.status_code in {401, 403}


@pytest.mark.django_db
def test_healthcheck_is_public(client):
    response = client.get(reverse("healthz"))
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_activity_detail_displays_analysis(client, django_user_model):
    user = django_user_model.objects.create_user(username="runner", password="secret")
    client.force_login(user)
    activity = Activity.objects.create(
        strava_activity_id="analyzed-run",
        name="Morning Run",
        start_time="2026-09-13T06:00:00Z",
        sport_type="Run",
        distance=20000,
        moving_time=5700,
        elapsed_time=5700,
        analysis="活動判讀\n這是一堂長距離課。",
    )

    response = client.get(reverse("activity_detail", args=[activity.strava_activity_id]))

    content = response.content.decode()
    assert response.status_code == 200
    assert "活動分析與建議" in content
    assert "這是一堂長距離課" in content
