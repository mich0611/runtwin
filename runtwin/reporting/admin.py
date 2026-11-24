from django.contrib import admin

from .models import InsightEvidence, WeeklyReport

admin.site.register(WeeklyReport)
admin.site.register(InsightEvidence)
