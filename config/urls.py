from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from runtwin.web import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path(f"webhooks/strava/{settings.STRAVA_WEBHOOK_PATH_TOKEN}", views.strava_webhook, name="strava_webhook"),
    path("", include("runtwin.web.urls")),
]
