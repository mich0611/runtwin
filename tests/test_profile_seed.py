from datetime import timedelta

import pytest
from django.core.management import call_command

from runtwin.athletes.models import AthleteProfile


@pytest.mark.django_db
def test_seed_creates_blank_non_personal_profile():
    call_command("seed_athlete_profile")

    athlete = AthleteProfile.objects.get()
    assert athlete.half_marathon_pb is None
    assert athlete.half_marathon_goal is None
    assert athlete.marathon_goal is None
    assert athlete.normal_weekly_distance == 0
    assert athlete.runs_per_week == ""
    assert athlete.weekday_distance_limit == 0
    assert athlete.preferred_long_run_days == []
    assert athlete.provisional_tempo_hr_low is None
    assert athlete.provisional_tempo_hr_high is None
    assert athlete.observed_hr_max is None
    assert athlete.garmin_vo2max_reference_low is None
    assert athlete.garmin_vo2max_reference_high is None
    assert athlete.notes == ""


@pytest.mark.django_db
def test_seed_does_not_overwrite_existing_profile(athlete):
    athlete.half_marathon_goal = timedelta(hours=1, minutes=20)
    athlete.notes = "custom"
    athlete.save()
    call_command("seed_athlete_profile")
    athlete.refresh_from_db()
    assert athlete.half_marathon_goal == timedelta(hours=1, minutes=20)
    assert athlete.notes == "custom"
