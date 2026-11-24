from django.urls import path

from . import api_views, views

urlpatterns = [
    path("", views.home_redirect, name="home"),
    path("healthz", views.healthz, name="healthz"),
    path("weekly", views.weekly_latest, name="weekly_latest"),
    path("weekly/history", views.weekly_history, name="weekly_history"),
    path("weekly/<slug:week_start>", views.weekly_detail, name="weekly_detail"),
    path("check-in", views.check_in, name="check_in"),
    path("activities/<str:activity_id>", views.activity_detail, name="activity_detail"),
    path("api/weekly", api_views.WeeklyReportListApi.as_view(), name="api_weekly"),
    path("api/weekly/<str:week_start>", api_views.WeeklyReportDetailApi.as_view(), name="api_weekly_detail"),
    path("api/activities/<str:activity_id>", api_views.ActivityDetailApi.as_view(), name="api_activity_detail"),
]
