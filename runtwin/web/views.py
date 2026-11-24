from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from zoneinfo import ZoneInfo

from runtwin.activities.models import Activity
from runtwin.activities.webhook import enqueue_webhook_event
from runtwin.athletes.forms import WellbeingCheckInForm
from runtwin.athletes.models import AthleteProfile, WellbeingCheckIn
from runtwin.ai.progress import get_progress_narrative
from runtwin.progress.analysis import build_progress_analysis
from runtwin.reporting.models import WeeklyReport
from runtwin.reporting.periods import normalize_week_start


def home_redirect(request: HttpRequest) -> HttpResponse:
    return redirect("weekly_latest")


def healthz(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok"})


@csrf_exempt
def strava_webhook(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        if request.GET.get("hub.mode") != "subscribe":
            return JsonResponse({"error": "invalid mode"}, status=400)
        verify_token = request.GET.get("hub.verify_token", "")
        if not settings.STRAVA_WEBHOOK_VERIFY_TOKEN or not hmac.compare_digest(
            verify_token.encode("utf-8"), settings.STRAVA_WEBHOOK_VERIFY_TOKEN.encode("utf-8")
        ):
            return JsonResponse({"error": "invalid verify token"}, status=403)
        challenge = request.GET.get("hub.challenge")
        if not challenge:
            return JsonResponse({"error": "missing challenge"}, status=400)
        return JsonResponse({"hub.challenge": challenge})

    if request.method != "POST":
        response = JsonResponse({"error": "method not allowed"}, status=405)
        response["Allow"] = "GET, POST"
        return response
    if not settings.STRAVA_WEBHOOK_SUBSCRIPTION_ID or not settings.STRAVA_ATHLETE_ID:
        return JsonResponse({"error": "webhook not configured"}, status=503)
    if not _valid_strava_signature(request):
        return JsonResponse({"error": "invalid signature"}, status=401)
    if len(request.body) > 64 * 1024:
        return JsonResponse({"error": "payload too large"}, status=413)
    try:
        payload = json.loads(request.body)
        if not isinstance(payload, dict):
            raise ValueError
        if not _expected_strava_event(payload):
            return JsonResponse({"accepted": True, "ignored": True})
        event, created = enqueue_webhook_event(payload)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return JsonResponse({"error": "invalid payload"}, status=400)
    return JsonResponse({"accepted": True, "event_id": event.pk, "duplicate": not created})


def _expected_strava_event(payload: dict) -> bool:
    try:
        subscription_matches = (
            not settings.STRAVA_WEBHOOK_SUBSCRIPTION_ID
            or str(int(payload.get("subscription_id"))) == settings.STRAVA_WEBHOOK_SUBSCRIPTION_ID
        )
        owner_matches = (
            not settings.STRAVA_ATHLETE_ID
            or str(int(payload.get("owner_id"))) == settings.STRAVA_ATHLETE_ID
        )
    except (TypeError, ValueError):
        return False
    return subscription_matches and owner_matches


def _valid_strava_signature(request: HttpRequest) -> bool:
    secret = settings.STRAVA_WEBHOOK_SIGNING_SECRET
    if not secret:
        return not settings.STRAVA_WEBHOOK_REQUIRE_SIGNATURE
    header = request.headers.get("X-Strava-Signature", "")
    parts = dict(
        item.strip().split("=", 1)
        for item in header.split(",")
        if "=" in item
    )
    timestamp = parts.get("t", "")
    signature = parts.get("v1", "")
    try:
        if abs(time.time() - int(timestamp)) > settings.STRAVA_WEBHOOK_SIGNATURE_TOLERANCE_SECONDS:
            return False
    except ValueError:
        return False
    signed = timestamp.encode("ascii") + b"." + request.body
    expected = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return bool(signature) and hmac.compare_digest(signature, expected)


def _report_context(report: WeeklyReport | None) -> dict:
    progress = build_progress_analysis()
    progress_narrative = get_progress_narrative(progress)
    if not report:
        return {"report": None, "progress": progress, "progress_narrative": progress_narrative}
    facts = report.facts_json or {}
    ai = report.report_json or {}
    trends = facts.get("trends", {}).get("six_week", [])
    distribution = facts.get("workout_distribution", {})
    chart_payload = {
        "labels": [item["week_start"] for item in trends],
        "distance": [item["distance_km"] for item in trends],
        "elevation": [item["elevation_m"] for item in trends],
        "classes": [key for key, value in distribution.items() if value.get("value")],
        "classValues": [value["value"] for value in distribution.values() if value.get("value")],
    }
    return {
        "report": report,
        "facts": facts,
        "ai": ai,
        "progress": progress,
        "progress_narrative": progress_narrative,
        "chart_payload": json.dumps(chart_payload, ensure_ascii=False),
    }


@login_required
def weekly_latest(request: HttpRequest) -> HttpResponse:
    report = WeeklyReport.objects.order_by("-week_start").first()
    return render(request, "web/weekly.html", _report_context(report))


@login_required
def weekly_history(request: HttpRequest) -> HttpResponse:
    return render(request, "web/history.html", {"reports": WeeklyReport.objects.order_by("-week_start")})


@login_required
def weekly_detail(request: HttpRequest, week_start: str) -> HttpResponse:
    report = get_object_or_404(WeeklyReport, week_start=week_start)
    return render(request, "web/weekly.html", _report_context(report))


@login_required
def check_in(request: HttpRequest) -> HttpResponse:
    athlete = AthleteProfile.objects.order_by("id").first()
    if not athlete:
        raise Http404("尚未建立 AthleteProfile")
    local_today = timezone.now().astimezone(ZoneInfo(athlete.timezone)).date()
    week_start = normalize_week_start(local_today)
    instance = WellbeingCheckIn.objects.filter(athlete=athlete, week_start=week_start).first()
    if request.method == "POST":
        form = WellbeingCheckInForm(request.POST, instance=instance)
        if form.is_valid():
            item = form.save(commit=False)
            item.athlete = athlete
            item.week_start = week_start
            item.save()
            messages.success(request, "本週主觀狀態已儲存。")
            return redirect("check_in")
    else:
        form = WellbeingCheckInForm(instance=instance)
    return render(request, "web/check_in.html", {"form": form, "week_start": week_start})


@login_required
def activity_detail(request: HttpRequest, activity_id: str) -> HttpResponse:
    activity = get_object_or_404(Activity, strava_activity_id=activity_id)
    return render(request, "web/activity_detail.html", {"activity": activity})
