from django.contrib import admin
from .models import AlertEvent, DetectionSettings, MonitoringSession

admin.site.register(DetectionSettings)
admin.site.register(MonitoringSession)
admin.site.register(AlertEvent)
