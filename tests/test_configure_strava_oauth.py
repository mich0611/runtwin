from pathlib import Path

import pytest

from scripts.configure_strava_oauth import missing_scopes, update_env


@pytest.mark.parametrize(
    ("granted", "expected"),
    [
        ("read,activity:read_all,activity:write", []),
        ("read,activity:read_all", ["activity:write"]),
        ("read", ["activity:read_all", "activity:write"]),
        ("", []),
    ],
)
def test_missing_scopes_detects_unticked_permissions(granted, expected):
    assert missing_scopes("activity:read_all,activity:write", granted) == expected


def test_update_env_replaces_credentials_without_touching_other_settings(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DJANGO_SECRET_KEY=keep-me\n"
        "STRAVA_CLIENT_ID=old\n"
        "STRAVA_CLIENT_SECRET=old-secret\n"
        "STRAVA_REFRESH_TOKEN=old-refresh\n",
        encoding="utf-8",
    )

    update_env(env_file, {
        "STRAVA_CLIENT_ID": "123",
        "STRAVA_CLIENT_SECRET": "new-secret",
        "STRAVA_REFRESH_TOKEN": "new-refresh",
        "STRAVA_ATHLETE_ID": "456",
    })

    content = env_file.read_text(encoding="utf-8")
    assert "DJANGO_SECRET_KEY=keep-me" in content
    assert "STRAVA_CLIENT_ID=123" in content
    assert "STRAVA_CLIENT_SECRET=new-secret" in content
    assert "STRAVA_REFRESH_TOKEN=new-refresh" in content
    assert "STRAVA_ATHLETE_ID=456" in content
    assert "old-secret" not in content
    assert "old-refresh" not in content
