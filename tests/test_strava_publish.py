import json
from io import BytesIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from runtwin.activities.models import Activity
from runtwin.providers.strava_publish import (
    ANALYSIS_END,
    ANALYSIS_START,
    merge_analysis_into_description,
    publish_activity_analysis,
    strip_analysis_from_description,
)
from runtwin.providers.strava_write import StravaWriteClient


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_merge_analysis_preserves_original_and_replaces_existing_block():
    first = merge_analysis_into_description("Original note", "First analysis")
    second = merge_analysis_into_description(first, "Updated analysis")

    assert second.startswith("Original note")
    assert "First analysis" not in second
    assert "Updated analysis" in second
    assert second.count(ANALYSIS_START) == 1
    assert second.count(ANALYSIS_END) == 1


def test_merge_analysis_replaces_runtwin_legacy_block_with_new_brand():
    legacy = "Original note\n\n--- RunTwin 分析 ---\nOld analysis\n--- /RunTwin 分析 ---"

    merged = merge_analysis_into_description(legacy, "Updated analysis")

    assert "RunTwin 分析" not in merged
    assert merged.count(ANALYSIS_START) == 1
    assert merged.count(ANALYSIS_END) == 1
    assert "Updated analysis" in merged
    assert strip_analysis_from_description(legacy) == "Original note"


def test_merge_analysis_collapses_duplicate_legacy_blocks():
    first = merge_analysis_into_description("Original note", "First")
    duplicated = f"{first}\n\n{ANALYSIS_START}\nSecond\n{ANALYSIS_END}"

    merged = merge_analysis_into_description(duplicated, "Latest")

    assert merged.count(ANALYSIS_START) == 1
    assert merged.count(ANALYSIS_END) == 1
    assert "First" not in merged
    assert "Second" not in merged
    assert "Latest" in merged
    assert strip_analysis_from_description(duplicated) == "Original note"


def test_strip_analysis_returns_only_user_description():
    merged = merge_analysis_into_description("Original note", "Analysis")
    assert strip_analysis_from_description(merged) == "Original note"


def test_merge_analysis_is_noop_when_block_already_matches():
    description = merge_analysis_into_description("Original note", "Analysis")
    assert merge_analysis_into_description(description, "Analysis") == description


def test_strava_client_refreshes_token_and_persists_rotation(tmp_path):
    calls = []

    def opener(request, timeout):
        calls.append(request)
        if request.full_url.endswith("/oauth/token"):
            assert b"grant_type=refresh_token" in request.data
            return FakeResponse({
                "access_token": "new-access",
                "refresh_token": "new-refresh",
                "expires_at": 4102444800,
            })
        assert request.get_header("Authorization") == "Bearer new-access"
        return FakeResponse({"id": 123, "description": "Existing"})

    token_file = tmp_path / "strava-token.json"
    token_file.write_text(json.dumps({"refresh_token": "old-refresh", "scope": "activity:read activity:write"}), encoding="utf-8")
    client = StravaWriteClient("client", "secret", "old-refresh", token_file, opener=opener, clock=lambda: 0)

    activity = client.get_activity("123")

    assert activity["id"] == 123
    saved = json.loads(token_file.read_text(encoding="utf-8"))
    assert saved["refresh_token"] == "new-refresh"
    assert saved["scope"] == "activity:read activity:write"
    assert len(calls) == 2


def test_strava_client_updates_name_and_description_with_one_request(tmp_path):
    token_file = tmp_path / "strava-token.json"
    token_file.write_text(json.dumps({"access_token": "access", "refresh_token": "refresh", "expires_at": 9999, "scope": "activity:read,activity:write"}), encoding="utf-8")
    captured = {}

    def opener(request, timeout):
        captured["method"] = request.get_method()
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse({"id": 123, **captured["payload"]})

    client = StravaWriteClient("client", "secret", token_file=token_file, opener=opener, clock=lambda: 0)
    result = client.update_activity("123", name="[Easy] Morning Run", description="分析內容")

    assert captured == {
        "method": "PUT",
        "payload": {"name": "[Easy] Morning Run", "description": "分析內容"},
    }
    assert result["name"] == "[Easy] Morning Run"


def test_strava_client_updates_description_with_json_body(tmp_path):
    token_file = tmp_path / "strava-token.json"
    token_file.write_text(json.dumps({"access_token": "access", "refresh_token": "refresh", "expires_at": 9999, "scope": "activity:read,activity:write"}), encoding="utf-8")
    captured = {}

    def opener(request, timeout):
        if request.get_method() == "GET":
            return FakeResponse({"id": 123, "name": "Morning Run", "description": "Existing"})
        captured["method"] = request.get_method()
        captured["url"] = request.full_url
        captured["authorization"] = request.get_header("Authorization")
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse({"id": 123, **captured["payload"]})

    client = StravaWriteClient("client", "secret", token_file=token_file, opener=opener, clock=lambda: 0)
    result = client.update_activity_description("123", "分析內容")

    assert captured == {
        "method": "PUT",
        "url": "https://www.strava.com/api/v3/activities/123",
        "authorization": "Bearer access",
        "payload": {"name": "Morning Run", "description": "分析內容"},
    }
    assert result["description"] == "分析內容"


class FakeClient:
    def __init__(self):
        self.updated = None

    def get_activity(self, activity_id):
        return {"id": int(activity_id), "name": "Morning Run", "description": "Original note"}

    def update_activity(self, activity_id, *, name, description):
        self.updated = (activity_id, name, description)
        return {"id": int(activity_id), "name": name, "description": description}


@pytest.mark.django_db
def test_publish_activity_analysis_targets_matching_activity_and_supports_dry_run():
    activity = Activity.objects.create(
        strava_activity_id="123456789",
        name="Run",
        start_time="2026-09-13T06:00:00Z",
        sport_type="Run",
        distance=10000,
        moving_time=3000,
        elapsed_time=3000,
        analysis="活動分析內容",
    )
    client = FakeClient()

    preview = publish_activity_analysis(activity, client, dry_run=True)
    assert preview["updated"] is False
    assert client.updated is None
    assert "Original note" in preview["description"]
    assert "活動分析內容" in preview["description"]

    result = publish_activity_analysis(activity, client)
    assert result["updated"] is True


@pytest.mark.django_db
def test_publish_activity_analysis_reuses_supplied_remote_payload():
    activity = Activity.objects.create(
        strava_activity_id="123456789",
        name="Run",
        start_time="2026-09-13T06:00:00Z",
        sport_type="Run",
        distance=10000,
        moving_time=3000,
        elapsed_time=3000,
        analysis="活動分析內容",
    )
    client = FakeClient()
    client.get_activity = lambda activity_id: (_ for _ in ()).throw(AssertionError("must reuse payload"))

    result = publish_activity_analysis(
        activity,
        client,
        remote={"id": 123456789, "name": "Morning Run", "description": "Original note"},
    )

    assert result["updated"] is True
    assert client.updated[0] == "123456789"
    assert client.updated[0] == "123456789"
    assert client.updated[1] == "[Run] Morning Run"
    assert "活動分析內容" in client.updated[2]


@pytest.mark.django_db
def test_publish_command_requires_explicit_confirmation():
    Activity.objects.create(
        strava_activity_id="123456789",
        name="Run",
        start_time="2026-09-13T06:00:00Z",
        sport_type="Run",
        distance=10000,
        moving_time=3000,
        elapsed_time=3000,
        analysis="活動分析內容",
    )

    with pytest.raises(CommandError, match="--yes"):
        call_command("publish_activity_analysis", "123456789", stdout=BytesIO())
