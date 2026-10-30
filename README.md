# DrowsyGuard - Driver Drowsiness Detection (OpenCV + MediaPipe + Django)

## Run kaise kare (Windows)
Tere system me mediapipe 0.10.14 aur opencv already installed hai, to sirf Django chahiye:

    python -m pip install django
    cd drowsiness_project
    python manage.py migrate
    python manage.py runserver

Browser me kholo: http://127.0.0.1:8000

(Fresh laptop pe sab ek saath: `python -m pip install -r requirements.txt`, Python 3.10-3.12 best hai.)

## Pages
- Dashboard (/)      : Live camera, Start/Stop, Auto-Calibrate, Drowsiness Score gauge, live EAR/MAR chart, recent alerts, alarm sound
- History (/history/): Last 7 days chart, sessions table, alert log, CSV export
- Settings (/settings/): EAR/MAR thresholds, closed-eye time, camera index, alarm on/off
- Admin (/admin/)    : `python manage.py createsuperuser` ke baad

## Kaise kaam karta hai
1. MediaPipe Face Mesh (ML model) har frame me 468 face landmarks nikalta hai
2. EAR  = (|p2-p6| + |p3-p5|) / (2 * |p1-p4|)  -> aankh band/khuli
3. MAR  = muh ka vertical / horizontal ratio   -> yawning
4. PERCLOS = pichhle 30 sec me aankh band rehne ka %
5. Drowsiness Score = 45% PERCLOS + 40% eyes-closed-time + 15% yawn  (0-100)
6. Status: AWAKE / TIRED (score>=35) / YAWNING / DROWSY / NO FACE
7. Django camera ko background thread me chalata hai, MJPEG stream browser ko deta hai,
   alerts SQLite DB me save hote hain.

## Libraries
Backend : Django, OpenCV, MediaPipe, NumPy
Frontend: Tailwind CSS, Alpine.js, Chart.js, Lucide icons, Web Audio API (alarm)
(Frontend libraries CDN se aati hain, to demo ke time internet on rakhna.)

## Tips
- Pehli baar Start dabane pe 1-2 sec lagte hain (model load hota hai).
- Demo se pehle Auto-Calibrate zaroor kar lo, threshold tumhari aankh ke hisaab se set ho jata hai.
- Camera na khule to Settings me camera index 1 try karo, aur Zoom/Teams band karo.
