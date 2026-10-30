from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class DetectionSettings(models.Model):
    """Single-row table: dashboard se tune hone wale thresholds."""
    ear_threshold = models.FloatField(default=0.21, validators=[MinValueValidator(0.10), MaxValueValidator(0.40)])
    mar_threshold = models.FloatField(default=0.60, validators=[MinValueValidator(0.30), MaxValueValidator(1.20)])
    closed_seconds = models.FloatField(default=1.5, validators=[MinValueValidator(0.3), MaxValueValidator(5.0)])
    yawn_seconds = models.FloatField(default=1.0, validators=[MinValueValidator(0.3), MaxValueValidator(5.0)])
    camera_index = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(10)])
    show_landmarks = models.BooleanField(default=True)
    sound_enabled = models.BooleanField(default=True)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "Detection settings"


class MonitoringSession(models.Model):
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    drowsy_alerts = models.IntegerField(default=0)
    yawns = models.IntegerField(default=0)
    blinks = models.IntegerField(default=0)
    avg_ear = models.FloatField(default=0.0)
    peak_score = models.FloatField(default=0.0)

    class Meta:
        ordering = ["-started_at"]

    @property
    def duration(self):
        if not self.ended_at:
            return None
        secs = int((self.ended_at - self.started_at).total_seconds())
        return f"{secs // 60}m {secs % 60}s"

    def __str__(self):
        return f"Session {self.pk}"


class AlertEvent(models.Model):
    DROWSY = "DROWSY"
    YAWN = "YAWN"
    KINDS = [(DROWSY, "Drowsy"), (YAWN, "Yawn")]

    session = models.ForeignKey(MonitoringSession, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=10, choices=KINDS)
    created_at = models.DateTimeField(auto_now_add=True)
    ear = models.FloatField(default=0.0)
    mar = models.FloatField(default=0.0)
    duration = models.FloatField(default=0.0)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.kind} @ {self.created_at:%H:%M:%S}"
