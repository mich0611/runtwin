from __future__ import annotations

import json
import os
import re
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings

STRAVA_OAUTH_URL = "https://www.strava.com/oauth/token"
DEFAULT_API_BASE_URL = "https://www.strava.com/api/v3"


class StravaConfigurationError(RuntimeError):
    pass


class StravaApiError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class StravaWriteClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str = "",
        token_file: str | Path | None = None,
        api_base_url: str = DEFAULT_API_BASE_URL,
        timeout: float = 20.0,
        opener: Callable[..., Any] = urlopen,
        clock: Callable[[], float] = time.time,
    ):
        if not client_id or not client_secret:
            raise StravaConfigurationError("缺少 STRAVA_CLIENT_ID 或 STRAVA_CLIENT_SECRET。")
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.token_file = Path(token_file) if token_file else None
        self.api_base_url = api_base_url.rstrip("/")
        self.timeout = timeout
        self.opener = opener
        self.clock = clock

    @classmethod
    def from_settings(cls) -> StravaWriteClient:
        return cls(
            client_id=settings.STRAVA_CLIENT_ID,
            client_secret=settings.STRAVA_CLIENT_SECRET,
            refresh_token=settings.STRAVA_REFRESH_TOKEN,
            token_file=settings.STRAVA_TOKEN_FILE,
            api_base_url=settings.STRAVA_API_BASE_URL,
        )

    def get_activity(self, activity_id: str) -> dict[str, Any]:
        activity_id = _numeric_activity_id(activity_id)
        return self._authenticated_request("GET", f"{self.api_base_url}/activities/{activity_id}")

    def get_activity_streams(self, activity_id: str) -> dict[str, Any]:
        activity_id = _numeric_activity_id(activity_id)
        keys = "time,distance,heartrate,velocity_smooth,altitude,grade_smooth,cadence,moving,latlng"
        query = urlencode({"keys": keys, "key_by_type": "true"})
        return self._authenticated_request(
            "GET",
            f"{self.api_base_url}/activities/{activity_id}/streams?{query}",
        )

    def list_activities(self, *, params: dict[str, str | int] | None = None) -> list[dict[str, Any]]:
        query = urlencode(params or {})
        url = f"{self.api_base_url}/athlete/activities"
        if query:
            url = f"{url}?{query}"
        result = self._authenticated_request("GET", url, expected_type=list)
        return [item for item in result if isinstance(item, dict)]

    def update_activity(self, activity_id: str, *, name: str, description: str) -> dict[str, Any]:
        activity_id = _numeric_activity_id(activity_id)
        return self._authenticated_request(
            "PUT",
            f"{self.api_base_url}/activities/{activity_id}",
            payload={"name": name, "description": description},
        )

    def update_activity_description(self, activity_id: str, description: str) -> dict[str, Any]:
        activity = self.get_activity(activity_id)
        return self.update_activity(activity_id, name=activity.get("name") or "Run", description=description)

    def _authenticated_request(self, method: str, url: str, **kwargs: Any) -> Any:
        try:
            return self._request_json(method, url, access_token=self._access_token(), **kwargs)
        except StravaApiError as exc:
            if exc.status_code != 401:
                raise
        self._expire_cached_access_token()
        return self._request_json(method, url, access_token=self._access_token(), **kwargs)

    def _access_token(self) -> str:
        with self._token_lock():
            token_data = self._read_token_data()
            access_token = token_data.get("access_token")
            expires_at = token_data.get("expires_at")
            if access_token and isinstance(expires_at, (int, float)) and expires_at > self.clock() + 3600:
                self._require_write_scope(token_data.get("scope"))
                return str(access_token)

            refresh_token = token_data.get("refresh_token") or self.refresh_token
            if not refresh_token:
                raise StravaConfigurationError("缺少 STRAVA_REFRESH_TOKEN，且 token 檔案內沒有 refresh_token。")
            refreshed = self._request_json(
                "POST",
                STRAVA_OAUTH_URL,
                form={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": str(refresh_token),
                },
            )
            if not refreshed.get("access_token") or not refreshed.get("refresh_token"):
                raise StravaApiError("Strava 更新憑證回應缺少 access_token 或 refresh_token。")
            refreshed = {**token_data, **refreshed}
            self._require_write_scope(refreshed.get("scope"))
            self._write_token_data(refreshed)
            return str(refreshed["access_token"])

    @contextmanager
    def _token_lock(self):
        if not self.token_file:
            yield
            return
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        lock_file = self.token_file.with_suffix(f"{self.token_file.suffix}.lock")
        handle = lock_file.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                if handle.tell() == 0 and handle.read(1) == b"":
                    handle.write(b"0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            try:
                handle.seek(0)
                if os.name == "nt":
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()

    def _expire_cached_access_token(self) -> None:
        with self._token_lock():
            token_data = self._read_token_data()
            if token_data:
                token_data["expires_at"] = 0
                self._write_token_data(token_data)

    def _read_token_data(self) -> dict[str, Any]:
        if not self.token_file or not self.token_file.exists():
            return {}
        try:
            payload = json.loads(self.token_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StravaConfigurationError(f"無法讀取 Strava token 檔案：{exc}") from exc
        if not isinstance(payload, dict):
            raise StravaConfigurationError("Strava token 檔案必須是 JSON 物件。")
        return payload

    def _write_token_data(self, payload: dict[str, Any]) -> None:
        if not self.token_file:
            return
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.token_file.with_suffix(f"{self.token_file.suffix}.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        temporary.replace(self.token_file)

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        form: dict[str, str] | None = None,
        access_token: str | None = None,
        expected_type: type = dict,
    ) -> Any:
        headers = {"Accept": "application/json", "User-Agent": "RunTwin/0.1"}
        data = None
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif form is not None:
            data = urlencode(form).encode("ascii")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        request = Request(url, data=data, headers=headers, method=method)
        try:
            with self.opener(request, timeout=self.timeout) as response:
                body = response.read()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise StravaApiError(f"Strava API 回傳 HTTP {exc.code}：{detail[:1000]}", exc.code) from exc
        except URLError as exc:
            raise StravaApiError(f"無法連線 Strava API：{exc.reason}") from exc
        try:
            decoded = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StravaApiError("Strava API 回傳無法解析的 JSON。") from exc
        if not isinstance(decoded, expected_type):
            expected_name = "物件" if expected_type is dict else "陣列"
            raise StravaApiError(f"Strava API 回傳格式不是 JSON {expected_name}。")
        return decoded

    @staticmethod
    def _require_write_scope(scope: Any) -> None:
        if not scope:
            return
        if isinstance(scope, str):
            scopes = {item for item in re.split(r"[\s,]+", scope.strip()) if item}
        elif isinstance(scope, list):
            scopes = {str(item) for item in scope}
        else:
            return
        if "activity:write" not in scopes:
            raise StravaConfigurationError("Strava OAuth token 缺少 activity:write 權限。")
        if not scopes.intersection({"activity:read", "activity:read_all"}):
            raise StravaConfigurationError("Strava OAuth token 缺少 activity:read；Only Me 活動需 activity:read_all。")


def _numeric_activity_id(activity_id: str) -> str:
    value = str(activity_id)
    if not value.isdigit():
        raise ValueError("Strava activity ID 必須是純數字。")
    return value
