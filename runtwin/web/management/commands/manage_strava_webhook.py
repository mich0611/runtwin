from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

PUSH_SUBSCRIPTIONS_URL = "https://www.strava.com/api/v3/push_subscriptions"


class Command(BaseCommand):
    help = "查看、建立或刪除目前 Strava 應用程式的 webhook subscription。"

    def add_arguments(self, parser):
        parser.add_argument("action", choices=["list", "create", "delete"])
        parser.add_argument("--subscription-id", type=int, help="delete 時必填。")

    def handle(self, *args, **options):
        action = options["action"]
        _require_settings(require_verify_token=action == "create")
        if action == "list":
            result = _request_json("GET", PUSH_SUBSCRIPTIONS_URL, params=_credentials())
        elif action == "create":
            if not settings.STRAVA_WEBHOOK_CALLBACK_URL:
                raise CommandError("create 需要 STRAVA_WEBHOOK_CALLBACK_URL。")
            form = {
                **_credentials(),
                "callback_url": settings.STRAVA_WEBHOOK_CALLBACK_URL,
                "verify_token": settings.STRAVA_WEBHOOK_VERIFY_TOKEN,
            }
            result = _request_json("POST", PUSH_SUBSCRIPTIONS_URL, form=form)
            if isinstance(result, dict) and result.get("id"):
                self.stdout.write(
                    self.style.WARNING(
                        "請將 subscription id "
                        f"{result['id']} 填入 STRAVA_WEBHOOK_SUBSCRIPTION_ID，並設定 STRAVA_ATHLETE_ID 後重啟服務。"
                    )
                )
        else:
            subscription_id = options["subscription_id"]
            if not subscription_id:
                raise CommandError("delete 需要 --subscription-id。")
            result = _request_json(
                "DELETE",
                f"{PUSH_SUBSCRIPTIONS_URL}/{subscription_id}",
                params=_credentials(),
            )
        self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))


def _credentials() -> dict[str, str]:
    return {
        "client_id": settings.STRAVA_CLIENT_ID,
        "client_secret": settings.STRAVA_CLIENT_SECRET,
    }


def _require_settings(*, require_verify_token: bool) -> None:
    required = ["STRAVA_CLIENT_ID", "STRAVA_CLIENT_SECRET"]
    if require_verify_token:
        required.extend(["STRAVA_WEBHOOK_VERIFY_TOKEN", "STRAVA_WEBHOOK_CALLBACK_URL", "STRAVA_WEBHOOK_PATH_TOKEN"])
    missing = [name for name in required if not getattr(settings, name)]
    if missing:
        raise CommandError("缺少設定：" + ", ".join(missing))
    if require_verify_token and settings.STRAVA_WEBHOOK_PATH_TOKEN == "not-configured":
        raise CommandError("STRAVA_WEBHOOK_PATH_TOKEN 尚未設定安全的隨機值。")
    if require_verify_token and settings.STRAVA_WEBHOOK_PATH_TOKEN not in settings.STRAVA_WEBHOOK_CALLBACK_URL:
        raise CommandError("STRAVA_WEBHOOK_CALLBACK_URL 必須包含 STRAVA_WEBHOOK_PATH_TOKEN。")


def _request_json(
    method: str,
    url: str,
    *,
    params: dict[str, str] | None = None,
    form: dict[str, str] | None = None,
):
    if params:
        url = f"{url}?{urlencode(params)}"
    data = urlencode(form).encode("utf-8") if form else None
    request = Request(url, data=data, method=method)
    if data:
        request.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urlopen(request, timeout=20) as response:
            body = response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise CommandError(f"Strava subscription API 回傳 HTTP {exc.code}：{detail[:1000]}") from exc
    except URLError as exc:
        raise CommandError(f"無法連線 Strava subscription API：{exc.reason}") from exc
    if not body:
        return {"ok": True}
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CommandError("Strava subscription API 回傳無法解析的 JSON。") from exc
