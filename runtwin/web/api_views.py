from rest_framework.generics import ListAPIView, RetrieveAPIView

from runtwin.activities.models import Activity
from runtwin.reporting.models import WeeklyReport
from .serializers import ActivitySerializer, WeeklyReportSerializer


class WeeklyReportListApi(ListAPIView):
    queryset = WeeklyReport.objects.order_by("-week_start")
    serializer_class = WeeklyReportSerializer


class WeeklyReportDetailApi(RetrieveAPIView):
    queryset = WeeklyReport.objects.all()
    serializer_class = WeeklyReportSerializer
    lookup_field = "week_start"


class ActivityDetailApi(RetrieveAPIView):
    queryset = Activity.objects.all()
    serializer_class = ActivitySerializer
    lookup_field = "strava_activity_id"
    lookup_url_kwarg = "activity_id"
