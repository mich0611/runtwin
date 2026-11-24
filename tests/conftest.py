from datetime import timedelta

import pytest

from runtwin.athletes.models import AthleteProfile


@pytest.fixture(autouse=True)
def no_external_services(settings):
    # Never reach a real Garmin account or LLM API from tests, even when .env enables them.
    settings.RUNTWIN_GARMIN_ENABLED = False
    settings.RUNTWIN_AI_PROVIDER = ""
    settings.ANTHROPIC_API_KEY = ""
    settings.OPENAI_API_KEY = ""


@pytest.fixture
def athlete(db):
    return AthleteProfile.objects.create(
        timezone="Asia/Taipei",
        half_marathon_pb=timedelta(hours=1, minutes=50),
        half_marathon_goal=timedelta(hours=1, minutes=45),
        marathon_goal=timedelta(hours=3, minutes=45),
        normal_weekly_distance=40,
        runs_per_week="4-5",
        weekday_distance_limit=12,
        preferred_long_run_days=["Saturday", "Sunday"],
        provisional_tempo_hr_low=165,
        provisional_tempo_hr_high=168,
        observed_hr_max=174,
    )
