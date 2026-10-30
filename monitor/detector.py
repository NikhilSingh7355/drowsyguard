"""
Core detection logic.
MediaPipe Face Mesh (ML model, 468 landmarks) -> EAR / MAR / PERCLOS -> Drowsiness Score
"""
import math
import time
from collections import deque

import cv2
import mediapipe as mp

LEFT_EYE = [362, 385, 387, 263, 373, 380]
RIGHT_EYE = [33, 160, 158, 133, 153, 144]
OUTER_LIPS = [61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291,
              375, 321, 405, 314, 17, 84, 181, 91, 146]
PERCLOS_WINDOW = 30.0  # seconds

COLORS = {  # BGR
    "AWAKE": (90, 200, 90),
    "TIRED": (0, 190, 255),
    "YAWNING": (0, 140, 255),
    "DROWSY": (60, 60, 255),
    "NO FACE": (160, 160, 160),
}


def _d(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def eye_aspect_ratio(p):
    return (_d(p[1], p[5]) + _d(p[2], p[4])) / (2.0 * _d(p[0], p[3]) + 1e-6)


class DrowsinessDetector:
    def __init__(self):
        self.face_mesh = mp.solutions.face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self.reset()

    def reset(self):
        self.eye_closed_start = None
        self.yawn_start = None
        self.yawn_counted = False
        self.drowsy_active = False
        self.window = deque()  # (timestamp, eyes_closed)
        self.blinks = 0
        self.drowsy_alerts = 0
        self.yawns = 0

    def close(self):
        self.face_mesh.close()

    def process(self, frame, cfg):
        """Returns (annotated_frame, metrics_dict, events_list)."""
        now = time.time()
        h, w = frame.shape[:2]
        res = self.face_mesh.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

        events = []
        ear = mar = closed_for = 0.0
        face = False
        yawning = drowsy = False
        eyes_pts, lips_pts = [], []

        if res.multi_face_landmarks:
            face = True
            lm = res.multi_face_landmarks[0].landmark

            def pt(i):
                return (lm[i].x * w, lm[i].y * h)

            left = [pt(i) for i in LEFT_EYE]
            right = [pt(i) for i in RIGHT_EYE]
            ear = (eye_aspect_ratio(left) + eye_aspect_ratio(right)) / 2.0
            mar = _d(pt(13), pt(14)) / (_d(pt(78), pt(308)) + 1e-6)
            eyes_pts = [left, right]
            lips_pts = [pt(i) for i in OUTER_LIPS]

            # ---- eyes: blink / drowsy state machine ----
            closed = ear < cfg.ear_threshold
            if closed:
                if self.eye_closed_start is None:
                    self.eye_closed_start = now
                closed_for = now - self.eye_closed_start
            else:
                if self.eye_closed_start is not None:
                    d = now - self.eye_closed_start
                    if 0.04 <= d < cfg.closed_seconds:
                        self.blinks += 1
                self.eye_closed_start = None
                self.drowsy_active = False

            drowsy = closed_for >= cfg.closed_seconds
            if drowsy and not self.drowsy_active:
                self.drowsy_active = True
                self.drowsy_alerts += 1
                events.append(("DROWSY", ear, mar, closed_for))

            # ---- mouth: yawn ----
            if mar > cfg.mar_threshold:
                if self.yawn_start is None:
                    self.yawn_start = now
                yawning = (now - self.yawn_start) >= cfg.yawn_seconds
                if yawning and not self.yawn_counted:
                    self.yawn_counted = True
                    self.yawns += 1
                    events.append(("YAWN", ear, mar, now - self.yawn_start))
            else:
                self.yawn_start = None
                self.yawn_counted = False

            # ---- PERCLOS (rolling 30s) ----
            self.window.append((now, closed))
        else:
            self.eye_closed_start = None
            self.yawn_start = None
            self.drowsy_active = False

        while self.window and now - self.window[0][0] > PERCLOS_WINDOW:
            self.window.popleft()
        perclos = (sum(1 for _, c in self.window if c) / len(self.window)) if self.window else 0.0

        # ---- Drowsiness score (0-100) ----
        score = 100.0 * (
            0.45 * min(perclos / 0.30, 1.0)
            + 0.40 * min(closed_for / max(cfg.closed_seconds, 0.1), 1.0)
            + 0.15 * (1.0 if yawning else 0.0)
        ) if face else 0.0

        if not face:
            status = "NO FACE"
        elif drowsy:
            status = "DROWSY"
        elif yawning:
            status = "YAWNING"
        elif score >= 35:
            status = "TIRED"
        else:
            status = "AWAKE"

        self._draw(frame, status, face, eyes_pts, lips_pts, ear, mar, score, cfg, now)

        metrics = dict(
            face=face, status=status,
            ear=round(ear, 3), mar=round(mar, 3),
            perclos=round(perclos * 100, 1), score=round(score, 1),
            blinks=self.blinks, drowsy_alerts=self.drowsy_alerts, yawns=self.yawns,
            closed_for=round(closed_for, 2),
        )
        return frame, metrics, events

    def _draw(self, frame, status, face, eyes, lips, ear, mar, score, cfg, now):
        h, w = frame.shape[:2]
        color = COLORS[status]
        if face and cfg.show_landmarks:
            import numpy as np
            for eye in eyes:
                cv2.polylines(frame, [np.array(eye, np.int32)], True, (255, 220, 0), 1, cv2.LINE_AA)
            cv2.polylines(frame, [np.array(lips, np.int32)], True, (255, 120, 200), 1, cv2.LINE_AA)

        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, 40), (15, 15, 15), -1)
        cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)
        cv2.putText(frame, status, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2, cv2.LINE_AA)
        cv2.putText(frame, f"EAR {ear:.2f}  MAR {mar:.2f}  SCORE {score:.0f}", (w - 330, 27),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (230, 230, 230), 1, cv2.LINE_AA)
        if status == "DROWSY" and int(now * 4) % 2 == 0:
            cv2.rectangle(frame, (0, 0), (w - 1, h - 1), color, 10)
