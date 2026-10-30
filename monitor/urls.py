from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("history/", views.history, name="history"),
    path("history/clear/", views.clear_history, name="clear_history"),
    path("settings/", views.settings_view, name="settings"),
    path("video_feed/", views.video_feed, name="video_feed"),
    path("export/events.csv", views.export_csv, name="export_csv"),
    path("api/status/", views.api_status, name="api_status"),
    path("api/start/", views.api_start, name="api_start"),
    path("api/stop/", views.api_stop, name="api_stop"),
    path("api/calibrate/", views.api_calibrate, name="api_calibrate"),
]
