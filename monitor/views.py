import csv
import json
import time
from datetime import timedelta

from django import forms
from django.contrib import messages
from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .camera import camera
from .models import AlertEvent, DetectionSettings, MonitoringSession


class SettingsForm(forms.ModelForm):
    class Meta:
        model = DetectionSettings
        fields = ["ear_threshold", "mar_threshold", "closed_seconds", "yawn_seconds",
                  "camera_index", "show_landmarks", "sound_enabled"]


def dashboard(request):
    return render(request, "monitor/dashboard.html", {"cfg": DetectionSettings.load(), "page": "dashboard"})


def history(request):
    today = timezone.localdate()
    start = today - timedelta(days=6)
    rows = (AlertEvent.objects.filter(created_at__date__gte=start)
            .annotate(day=TruncDate("created_at")).values("day", "kind").annotate(n=Count("id")))
    days = [start + timedelta(days=i) for i in range(7)]
    drowsy = {d: 0 for d in days}
    yawn = {d: 0 for d in days}
    for r in rows:
        (drowsy if r["kind"] == "DROWSY" else yawn)[r["day"]] += r["n"]
    chart = {
        "labels": [d.strftime("%d %b") for d in days],
        "drowsy": [drowsy[d] for d in days],
        "yawn": [yawn[d] for d in days],
    }
    totals = MonitoringSession.objects.aggregate(s=Count("id"), d=Sum("drowsy_alerts"), y=Sum("yawns"))
    ctx = {
        "page": "history",
        "sessions": MonitoringSession.objects.all()[:15],
        "events": AlertEvent.objects.select_related("session")[:40],
        "chart": chart,
        "totals": {"sessions": totals["s"] or 0, "drowsy": totals["d"] or 0, "yawns": totals["y"] or 0},
    }
    return render(request, "monitor/history.html", ctx)


def settings_view(request):
    cfg = DetectionSettings.load()
    if request.method == "POST":
        form = SettingsForm(request.POST, instance=cfg)
        if form.is_valid():
            form.save()
            messages.success(request, "Settings save ho gayi. Chalte hue camera pe 1 sec me apply ho jayengi.")
            return redirect("settings")
        messages.error(request, "Kuch values galat hain: " + "; ".join(
            f"{k}: {', '.join(v)}" for k, v in form.errors.items()))
    return render(request, "monitor/settings.html", {"cfg": cfg, "page": "settings"})


def video_feed(request):
    def gen():
        while True:
            frame = camera.get_frame()
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            time.sleep(0.03 if camera.running else 0.25)

    resp = StreamingHttpResponse(gen(), content_type="multipart/x-mixed-replace; boundary=frame")
    resp["Cache-Control"] = "no-store"
    return resp


def api_status(request):
    data = camera.get_status()
    cfg = DetectionSettings.load()
    data["thr"] = {"ear": cfg.ear_threshold, "mar": cfg.mar_threshold}
    data["recent"] = [
        {"kind": e.kind, "time": timezone.localtime(e.created_at).strftime("%H:%M:%S"),
         "ear": round(e.ear, 2), "duration": round(e.duration, 1)}
        for e in AlertEvent.objects.all()[:6]
    ]
    return JsonResponse(data)


@csrf_exempt
@require_POST
def api_start(request):
    camera.start()
    return JsonResponse({"ok": True})


@csrf_exempt
@require_POST
def api_stop(request):
    camera.stop()
    return JsonResponse({"ok": True})


@csrf_exempt
@require_POST
def api_calibrate(request):
    camera.calibrate(5)
    return JsonResponse({"ok": True})


def export_csv(request):
    resp = HttpResponse(content_type="text/csv")
    resp["Content-Disposition"] = 'attachment; filename="drowsiness_events.csv"'
    w = csv.writer(resp)
    w.writerow(["id", "session", "kind", "time", "ear", "mar", "duration_sec"])
    for e in AlertEvent.objects.all().order_by("created_at"):
        w.writerow([e.id, e.session_id, e.kind,
                    timezone.localtime(e.created_at).strftime("%Y-%m-%d %H:%M:%S"),
                    round(e.ear, 3), round(e.mar, 3), round(e.duration, 2)])
    return resp


@require_POST
def clear_history(request):
    camera.stop()
    AlertEvent.objects.all().delete()
    MonitoringSession.objects.all().delete()
    messages.success(request, "Saari history delete ho gayi.")
    return redirect("history")
