import json

from runtwin.providers.strava_api import StravaApiProvider
from runtwin.providers.strava_write import StravaApiError, StravaWriteClient


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def token_file(tmp_path):
    path = tmp_path / "token.json"
    path.write_text(
        json.dumps({
            "access_token": "access",
            "refresh_token": "refresh",
            "expires_at": 9999,
            "scope": "activity:read_all activity:write",
        }),
        encoding="utf-8",
    )
    return path


def test_strava_client_requests_all_supported_streams(tmp_path):
    captured = {}

    def opener(request, timeout):
        captured["url"] = request.full_url
        return FakeResponse({"time": {"data": [0, 1]}})

    client = StravaWriteClient("client", "secret", token_file=token_file(tmp_path), opener=opener, clock=lambda: 0)

    client.get_activity_streams("123")

    assert "/activities/123/streams?" in captured["url"]
    assert "heartrate" in captured["url"]
    assert "key_by_type=true" in captured["url"]


def test_strava_provider_treats_missing_streams_as_empty():
    class StreamlessClient:
        def get_activity_streams(self, activity_id):
            raise StravaApiError("missing", status_code=404)

    provider = StravaApiProvider(client=StreamlessClient(), activity_ids=["123"])

    assert provider.get_activity_streams("123") == {}


def test_strava_api_provider_lists_activities_with_time_bounds(tmp_path):
    captured = {}

    def opener(request, timeout):
        captured["url"] = request.full_url
        return FakeResponse([{"id": 123, "sport_type": "Run"}])

    client = StravaWriteClient("client", "secret", token_file=token_file(tmp_path), opener=opener, clock=lambda: 0)
    provider = StravaApiProvider(client=client)

    activities = list(provider.list_activities())

    assert activities == [{"id": 123, "sport_type": "Run"}]
    assert captured["url"].endswith("/athlete/activities?per_page=100&page=1")
