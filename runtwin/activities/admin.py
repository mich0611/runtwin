from django.contrib import admin

from .models import Activity, ActivityStream, DataSyncRun, StravaWebhookEvent

admin.site.register(Activity)
admin.site.register(ActivityStream)
admin.site.register(DataSyncRun)
admin.site.register(StravaWebhookEvent)
