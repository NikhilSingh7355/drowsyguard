"""
Background camera thread. Frames capture + detect karta hai,
latest JPEG aur metrics memory me rakhta hai; views unhe stream/serve karte hain.
"""
import os
import threading
import time
from collections import deque

import cv2
import numpy as np
from django.db import connection
from django.utils import timezone


def _placeholder_jpeg(text):
    img = np.zeros((480, 640, 3), np.uint8)
    img[:] = (30, 22, 16)
    size = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.9, 2)[0]
    cv2.putText(img, text, ((640 - size[0]) // 2, 245), cv2.FONT_HERSHEY_SIMPLEX,
                0.9, (190, 190, 190), 2, cv2.LINE_AA)
    return cv2.imencode(".jpg", img)[1].tobytes()


def _default_metrics():
    return dict(face=False, status="OFFLINE", ear=0.0, mar=0.0, perclos=0.0, score=0.0,
                blinks=0, drowsy_alerts=0, yawns=0, closed_for=0.0, fps=0.0, calibrating=0.0)


class CameraService:
    def __init__(self):
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._frame = None
        self._idle = _placeholder_jpeg("Camera OFF - press Start")
        self.running = False
        self.error = ""
        self.calib_msg = ""
        self._calib = None  # {"until": ts, "samples": []}
        self.metrics = _default_metrics()
        self.series = deque(maxlen=120)

    # ---------- public API ----------
    def start(self):
        with self._lock:
            if self.running:
                return
            self._stop.clear()
            self.error = ""
            self.running = True
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()
        t = self._thread
        if t:
            t.join(timeout=4)

    def calibrate(self, seconds=5):
        self.start()
        self.calib_msg = ""
        self._calib = {"until": time.time() + seconds, "samples": []}

    def get_frame(self):
        return self._frame if (self.running and self._frame) else self._idle

    def get_status(self):
        with self._lock:
            return dict(running=self.running, error=self.error, calib_msg=self.calib_msg,
                        metrics=dict(self.metrics), series=list(self.series))

    # ---------- worker ----------
    def _loop(self):
        from .detector import DrowsinessDetector
        from .models import AlertEvent, DetectionSettings, MonitoringSession

        cap = detector = session = None
        frames = 0
        ear_sum = peak = 0.0
        try:
            cfg = DetectionSettings.load()
            backend = cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY
            cap = cv2.VideoCapture(cfg.camera_index, backend)
            if not cap.isOpened():
                self.error = ("Camera open nahi hua. Settings me camera index (0/1) badal ke dekho "
                              "ya Zoom/Teams jaisi apps band karo.")
                return
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

            detector = DrowsinessDetector()
            session = MonitoringSession.objects.create()
            self.series.clear()
            last_cfg = last_series = last_t = time.time()
            fps = 0.0

            while not self._stop.is_set():
                ok, frame = cap.read()
                if not ok:
                    self.error = "Camera se frame nahi mil raha."
                    break
                now = time.time()
                if now - last_cfg > 1.0:
                    cfg = DetectionSettings.load()
                    last_cfg = now

                frame = cv2.flip(frame, 1)
                out, m, events = detector.process(frame, cfg)

                for kind, ear, mar, dur in events:
                    AlertEvent.objects.create(session=session, kind=kind, ear=ear, mar=mar, duration=dur)

                # calibration: aankh khuli rakh ke avg EAR -> threshold
                calibrating = 0.0
                c = self._calib
                if c:
                    if m["face"]:
                        c["samples"].append(m["ear"])
                    if now >= c["until"]:
                        if len(c["samples"]) >= 15:
                            mean = sum(c["samples"]) / len(c["samples"])
                            thr = round(max(0.12, min(0.35, mean * 0.72)), 2)
                            cfg.ear_threshold = thr
                            cfg.save(update_fields=["ear_threshold"])
                            self.calib_msg = f"Calibration done: avg open EAR {mean:.2f} -> threshold {thr}"
                        else:
                            self.calib_msg = "Calibration fail: chehra camera me clearly dikhna chahiye."
                        self._calib = None
                    else:
                        calibrating = round(c["until"] - now, 1)

                frames += 1
                ear_sum += m["ear"]
                peak = max(peak, m["score"])
                fps = 0.9 * fps + 0.1 * (1.0 / max(now - last_t, 1e-3))
                last_t = now
                m["fps"] = round(fps, 1)
                m["calibrating"] = calibrating

                jpeg = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, 80])[1].tobytes()
                with self._lock:
                    self._frame = jpeg
                    self.metrics = m
                    if now - last_series >= 0.25:
                        self.series.append({"ear": m["ear"], "mar": m["mar"], "score": m["score"]})
                        last_series = now
        except Exception as exc:  # noqa
            self.error = f"Error: {exc}"
        finally:
            if session:
                session.ended_at = timezone.now()
                if detector:
                    session.drowsy_alerts = detector.drowsy_alerts
                    session.yawns = detector.yawns
                    session.blinks = detector.blinks
                session.avg_ear = round(ear_sum / frames, 3) if frames else 0.0
                session.peak_score = round(peak, 1)
                session.save()
            if detector:
                detector.close()
            if cap:
                cap.release()
            with self._lock:
                self.running = False
                self._frame = None
                self._calib = None
                self.metrics = _default_metrics()
            connection.close()


camera = CameraService()
