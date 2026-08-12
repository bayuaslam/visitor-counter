import os
import cv2
import json
import sqlite3
import subprocess
import sys
import time
import re
from concurrent.futures import ThreadPoolExecutor
from collections import deque
from datetime import datetime, date
from getpass import getpass
from pathlib import Path
from urllib.parse import quote

from ultralytics import YOLO


DEFAULT_CAMERA_IP = "192.168.137.88"
CAMERA_MAC = "64-24-4d-81-4f-08"
CAMERA_IP = DEFAULT_CAMERA_IP

CONFIG_FILE = "line_config.json"
DB_FILE = "lab_visitors.db"
CREDENTIAL_FILE = Path("camera_password.dpapi")
HEARTBEAT_FILE = Path("counter_heartbeat")
RESET_REQUEST_FILE = Path("counter_reset.request")
HEADLESS = os.getenv("LABHUB_HEADLESS", "0") == "1" or Path(sys.executable).name.lower() == "pythonw.exe"

RTSP_PATH = "ch1/sub"
YOLO_IMGSZ = 512
CONF = 0.12

# Hysteresis crossing agar kaki yang jitter di sekitar garis tidak double count.
CROSS_MARGIN = 7

# Fallback khusus POV depan:
# kalau track baru pertama terlihat sedikit SESUDAH garis,
# arah geraknya tetap bisa dipakai untuk menentukan IN/OUT.
FALLBACK_ZONE = 125
FALLBACK_MIN_MOVE = 12
FALLBACK_MAX_AGE = 2.8

# Lebarkan sedikit area pintu dari dua titik garis yang dipilih.
DOOR_X_PADDING = 70


def load_saved_camera_password():
    if not CREDENTIAL_FILE.exists():
        return None
    decrypt_script = r"""
$encrypted = (Get-Content -Raw -LiteralPath $env:LABHUB_CREDENTIAL_PATH).Trim()
$secure = ConvertTo-SecureString $encrypted
$pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try { [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
"""
    decrypt_env = os.environ.copy()
    decrypt_env["LABHUB_CREDENTIAL_PATH"] = str(CREDENTIAL_FILE.resolve())
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", decrypt_script],
        capture_output=True,
        text=True,
        timeout=10,
        env=decrypt_env,
    )
    password = result.stdout.strip()
    if result.returncode != 0 or not password:
        if HEADLESS:
            raise RuntimeError("Kredensial CCTV tidak dapat dibuka oleh akun Windows yang menjalankan counter")
        print("Kredensial lama tidak cocok dengan akun Windows ini. Masukkan ulang sekali untuk menyimpannya kembali.")
        return None
    return password


def save_camera_password(password):
    encrypt_script = r"""
$secure = ConvertTo-SecureString $env:LABHUB_PASSWORD_TO_STORE -AsPlainText -Force
$encrypted = ConvertFrom-SecureString $secure
[IO.File]::WriteAllText($env:LABHUB_CREDENTIAL_PATH, $encrypted, [Text.Encoding]::ASCII)
"""
    encrypt_env = os.environ.copy()
    encrypt_env["LABHUB_PASSWORD_TO_STORE"] = password
    encrypt_env["LABHUB_CREDENTIAL_PATH"] = str(CREDENTIAL_FILE.resolve())
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", encrypt_script],
        capture_output=True,
        text=True,
        timeout=10,
        env=encrypt_env,
    )
    if result.returncode != 0:
        print("Peringatan: password dapat dipakai, tetapi gagal disimpan untuk startup berikutnya.")


def camera_ip_from_arp():
    result = subprocess.run(["arp.exe", "-a"], capture_output=True, text=True, timeout=10)
    target = CAMERA_MAC.replace(":", "-").lower()
    for line in result.stdout.splitlines():
        match = re.search(r"\b(\d{1,3}(?:\.\d{1,3}){3})\s+([0-9a-fA-F-]{17})\b", line)
        if match and match.group(2).lower() == target:
            candidate = match.group(1)
            check = subprocess.run(["ping.exe", "-n", "1", "-w", "400", candidate], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if check.returncode == 0:
                return candidate
    return None


def discover_camera_ip():
    override = os.getenv("LABHUB_CAMERA_IP")
    if override:
        return override
    discovered = camera_ip_from_arp()
    if discovered:
        print(f"CCTV EZVIZ ditemukan di {discovered}")
        return discovered
    prefix = ".".join(DEFAULT_CAMERA_IP.split(".")[:3])
    def ping(host):
        subprocess.run(["ping.exe", "-n", "1", "-w", "180", host], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with ThreadPoolExecutor(max_workers=40) as executor:
        list(executor.map(ping, (f"{prefix}.{number}" for number in range(1, 255))))
    discovered = camera_ip_from_arp()
    if discovered:
        print(f"CCTV EZVIZ ditemukan di {discovered}")
        return discovered
    print(f"CCTV tidak ditemukan otomatis, memakai alamat cadangan {DEFAULT_CAMERA_IP}")
    return DEFAULT_CAMERA_IP

# Minimal jeda event track yang sama.
EVENT_COOLDOWN = 1.2

os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"


# =========================================================
# CONFIG
# =========================================================

def save_config(p1, p2, invert):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {
                "p1": list(p1),
                "p2": list(p2),
                "invert": invert
            },
            f,
            indent=2
        )


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return None

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        return (
            tuple(data["p1"]),
            tuple(data["p2"]),
            bool(data.get("invert", False))
        )
    except Exception:
        return None


# =========================================================
# PILIH GARIS
# =========================================================

def select_line(frame):
    points = []
    win = "SET GARIS PINTU"

    cv2.namedWindow(win, cv2.WINDOW_NORMAL)

    def mouse_callback(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and len(points) < 2:
            points.append((x, y))

    cv2.setMouseCallback(win, mouse_callback)

    print("")
    print("======================================")
    print("SET GARIS PINTU")
    print("======================================")
    print("Klik 2 titik: ujung kiri dan kanan garis.")
    print("Buat garis melintang di jalur pintu.")
    print("")

    while True:
        display = frame.copy()

        cv2.putText(
            display,
            "KLIK 2 TITIK MELINTASI PINTU",
            (20, 35),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            (255, 255, 255),
            2
        )

        for p in points:
            cv2.circle(display, p, 7, (0, 0, 255), -1)

        if len(points) == 2:
            cv2.line(display, points[0], points[1], (0, 255, 255), 3)

        cv2.imshow(win, display)

        key = cv2.waitKey(30) & 0xFF

        if key == 27:
            raise SystemExit

        if len(points) == 2:
            cv2.waitKey(300)
            break

    cv2.destroyWindow(win)
    return points[0], points[1]


# =========================================================
# LINE MATH - khusus perspektif depan
# =========================================================

def line_y_at_x(x, p1, p2):
    x1, y1 = p1
    x2, y2 = p2

    if x2 == x1:
        return (y1 + y2) / 2.0

    t = (x - x1) / float(x2 - x1)
    return y1 + t * (y2 - y1)


def distance_from_line(point, p1, p2):
    """
    Nilai + berarti titik kaki berada di bawah garis pada gambar
    (lebih dekat ke kamera pada POV CCTV ini).
    Nilai - berarti berada di atas garis (lebih dekat pintu/luar).
    """
    x, y = point
    return y - line_y_at_x(x, p1, p2)


def in_door_x(point, p1, p2):
    x = point[0]
    lo = min(p1[0], p2[0]) - DOOR_X_PADDING
    hi = max(p1[0], p2[0]) + DOOR_X_PADDING
    return lo <= x <= hi


# =========================================================
# SQLITE DATABASE
# =========================================================

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS visitor_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                event_date TEXT NOT NULL,
                track_id INTEGER,
                direction TEXT NOT NULL CHECK(direction IN ('IN', 'OUT')),
                occupancy_after INTEGER NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_visitor_events_date
            ON visitor_events(event_date)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS counter_state (
                id INTEGER PRIMARY KEY CHECK(id = 1),
                occupancy INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            INSERT OR IGNORE INTO counter_state(id, occupancy, updated_at)
            VALUES(1, 0, ?)
        """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),))


def load_today_counts():
    today = date.today().isoformat()
    with get_db() as conn:
        row = conn.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN direction = 'IN' THEN 1 ELSE 0 END), 0),
                COALESCE(SUM(CASE WHEN direction = 'OUT' THEN 1 ELSE 0 END), 0)
            FROM visitor_events
            WHERE event_date = ?
        """, (today,)).fetchone()
    return int(row[0]), int(row[1])


def load_occupancy():
    with get_db() as conn:
        row = conn.execute("""
            SELECT occupancy
            FROM counter_state
            WHERE id = 1
        """).fetchone()
    return int(row[0]) if row else 0


def load_last_event():
    with get_db() as conn:
        row = conn.execute("""
            SELECT direction, timestamp
            FROM visitor_events
            ORDER BY id DESC
            LIMIT 1
        """).fetchone()
    if not row:
        return "-", ""
    direction, timestamp = row
    return direction, timestamp[11:19] if len(timestamp) >= 19 else timestamp


def save_event_db(track_id, direction, occupancy_after):
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    event_date = now.date().isoformat()

    with get_db() as conn:
        conn.execute("""
            INSERT INTO visitor_events(
                timestamp, event_date, track_id, direction, occupancy_after
            )
            VALUES (?, ?, ?, ?, ?)
        """, (timestamp, event_date, track_id, direction, occupancy_after))
        conn.execute("""
            UPDATE counter_state
            SET occupancy = ?, updated_at = ?
            WHERE id = 1
        """, (occupancy_after, timestamp))

    return timestamp


def clear_today_test_data():
    # Untuk fase testing. Saat production sebaiknya tombol reset ini dihapus.
    today = date.today().isoformat()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        conn.execute("DELETE FROM visitor_events WHERE event_date = ?", (today,))
        conn.execute("""
            UPDATE counter_state
            SET occupancy = 0, updated_at = ?
            WHERE id = 1
        """, (timestamp,))


# =========================================================
# CAMERA
# =========================================================

saved_password = os.getenv("LABHUB_CAMERA_PASSWORD") or load_saved_camera_password()
if not saved_password:
    saved_password = getpass("Password C6N: ")
    save_camera_password(saved_password)
password = quote(saved_password, safe="")
CAMERA_IP = discover_camera_ip()

rtsp_url = (
    f"rtsp://admin:{password}@{CAMERA_IP}:554/{RTSP_PATH}"
)

print("Loading YOLO...")
model = YOLO("yolo26n.pt")

print("Menghubungkan CCTV...")
cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)

try:
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
except Exception:
    pass

if not cap.isOpened():
    print("GAGAL membuka CCTV")
    raise SystemExit

ret, first_frame = cap.read()

if not ret:
    print("Gagal membaca frame CCTV")
    raise SystemExit


# =========================================================
# GARIS
# =========================================================

config = load_config()

if config is None:
    if HEADLESS:
        raise RuntimeError("Garis penghitung belum diatur. Jalankan visitor_counter.py dengan python.exe untuk mengatur garis.")
    p1, p2 = select_line(first_frame)
    invert_direction = False
    save_config(p1, p2, invert_direction)
else:
    p1, p2, invert_direction = config


# =========================================================
# STATE + LOAD DARI SQLITE
# =========================================================

init_db()

in_count, out_count = load_today_counts()
occupancy = load_occupancy()
last_event_text, last_event_clock = load_last_event()
current_day = date.today()

tracks = {}


def new_track_state(now, d):
    return {
        "first_seen": now,
        "first_d": d,
        "last_d": d,
        "history": deque(maxlen=12),
        "fallback_used": False,
        "last_event_time": 0.0,
    }


def apply_direction(track_id, direction):
    global in_count, out_count, occupancy
    global last_event_text, last_event_clock

    if invert_direction:
        direction = "OUT" if direction == "IN" else "IN"

    if direction == "IN":
        in_count += 1
        occupancy += 1
    else:
        out_count += 1
        occupancy = max(0, occupancy - 1)

    timestamp = save_event_db(
        track_id,
        direction,
        occupancy
    )

    last_event_text = direction
    last_event_clock = timestamp[11:19]

    print(
        f"[{timestamp}] Person #{track_id} -> {direction} | "
        f"IN={in_count} OUT={out_count} INSIDE={occupancy}"
    )


print("")
print("======================================")
print("VISITOR COUNTER + SQLITE AKTIF")
print("======================================")
print("ESC = keluar")
print("R   = gambar ulang garis")
print("I   = balik arah IN/OUT")
print("C   = HAPUS DATA TEST HARI INI + reset 0")
print("")
print("MODE: POV DEPAN + SQLite persistence")
print("")


# =========================================================
# LOOP
# =========================================================

last_heartbeat_write = 0.0

while True:
    if RESET_REQUEST_FILE.exists():
        clear_today_test_data()
        in_count = 0
        out_count = 0
        occupancy = 0
        last_event_text = "-"
        last_event_clock = ""
        tracks.clear()
        RESET_REQUEST_FILE.unlink(missing_ok=True)
        print("RESET COUNTER DITERIMA DARI DASHBOARD ADMIN")

    # Ganti hari otomatis tanpa restart program.
    if date.today() != current_day:
        current_day = date.today()
        in_count = 0
        out_count = 0
        last_event_text = "-"
        last_event_clock = ""
        print(f"HARI BARU: {current_day.isoformat()} - counter harian mulai 0")

    ret, frame = cap.read()

    if not ret:
        if cv2.waitKey(1) & 0xFF == 27:
            break
        continue

    heartbeat_now = time.time()
    if heartbeat_now - last_heartbeat_write >= 1:
        HEARTBEAT_FILE.write_text(json.dumps({"camera_ip": CAMERA_IP, "stream": RTSP_PATH, "mode": "Background"}), encoding="utf-8")
        last_heartbeat_write = heartbeat_now

    results = model.track(
        frame,
        persist=True,
        tracker="bytetrack.yaml",
        classes=[0],
        conf=CONF,
        imgsz=YOLO_IMGSZ,
        verbose=False
    )

    result = results[0]
    annotated = frame.copy()

    cv2.line(annotated, p1, p2, (0, 255, 255), 2)

    # Door region helper
    door_left = max(0, min(p1[0], p2[0]) - DOOR_X_PADDING)
    door_right = min(frame.shape[1] - 1, max(p1[0], p2[0]) + DOOR_X_PADDING)

    if result.boxes is not None:
        for box in result.boxes:
            if box.id is None:
                continue

            track_id = int(box.id[0].item())
            confidence = float(box.conf[0].item())
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())

            # Titik kaki = bawah tengah box
            foot = ((x1 + x2) // 2, y2)

            d = distance_from_line(foot, p1, p2)
            now = time.time()

            if track_id not in tracks:
                tracks[track_id] = new_track_state(now, d)

            st = tracks[track_id]
            st["history"].append((now, foot[0], foot[1], d))

            # Gambar person
            cv2.rectangle(
                annotated,
                (x1, y1),
                (x2, y2),
                (0, 255, 0),
                2
            )
            cv2.circle(annotated, foot, 5, (0, 0, 255), -1)

            # Gerak Y dari sampel awal ke terbaru.
            delta_y = 0.0
            if len(st["history"]) >= 4:
                delta_y = (
                    st["history"][-1][2]
                    -
                    st["history"][0][2]
                )

            cv2.putText(
                annotated,
                f"#{track_id} {confidence:.2f} d={d:.0f} dy={delta_y:.0f}",
                (x1, max(22, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.48,
                (0, 255, 0),
                1
            )

            can_event = (
                now - st["last_event_time"] >= EVENT_COOLDOWN
            )

            # =================================================
            # 1) CROSSING NORMAL
            # Atas -> bawah pada gambar = mendekati kamera = IN.
            # Bawah -> atas = menjauhi kamera/pintu = OUT.
            # =================================================
            prev_d = st["last_d"]

            if can_event and in_door_x(foot, p1, p2):
                if prev_d < -CROSS_MARGIN and d > CROSS_MARGIN:
                    apply_direction(track_id, "IN")
                    st["last_event_time"] = now

                elif prev_d > CROSS_MARGIN and d < -CROSS_MARGIN:
                    apply_direction(track_id, "OUT")
                    st["last_event_time"] = now

            # =================================================
            # 2) FALLBACK POV DEPAN
            # Kadang YOLO baru memberi ID setelah orang sudah melewati
            # ambang pintu. Kalau track BARU muncul dekat garis dan
            # jelas bergerak masuk/keluar, tetap dihitung.
            # =================================================
            age = now - st["first_seen"]

            if (
                can_event
                and not st["fallback_used"]
                and 4 <= len(st["history"]) <= 12
                and age <= FALLBACK_MAX_AGE
                and in_door_x(foot, p1, p2)
            ):
                first_d = st["first_d"]

                # Track pertama muncul sedikit di bawah garis dan
                # terus bergerak turun -> orang sedang MASUK.
                if (
                    0 < first_d <= FALLBACK_ZONE
                    and delta_y >= FALLBACK_MIN_MOVE
                ):
                    apply_direction(track_id, "IN")
                    st["last_event_time"] = now
                    st["fallback_used"] = True

                # Track pertama muncul sedikit di atas garis dan
                # terus bergerak naik -> orang sedang KELUAR.
                elif (
                    -FALLBACK_ZONE <= first_d < 0
                    and delta_y <= -FALLBACK_MIN_MOVE
                ):
                    apply_direction(track_id, "OUT")
                    st["last_event_time"] = now
                    st["fallback_used"] = True

            # Update distance HANYA kalau cukup jauh dari garis,
            # supaya jitter di sekitar garis tidak menghapus sisi lama.
            if abs(d) > CROSS_MARGIN:
                st["last_d"] = d

    # Bersihkan track lama supaya dictionary tidak tumbuh terus
    active_ids = set()

    if result.boxes is not None:
        for box in result.boxes:
            if box.id is not None:
                active_ids.add(int(box.id[0].item()))

    for tid in list(tracks.keys()):
        st = tracks[tid]
        if tid not in active_ids and time.time() - st["first_seen"] > 20:
            tracks.pop(tid, None)

    # =========================================================
    # DASHBOARD - COMPACT
    # =========================================================

    overlay = annotated.copy()
    cv2.rectangle(
        overlay,
        (8, 8),
        (230, 122),
        (0, 0, 0),
        -1
    )
    cv2.addWeighted(
        overlay,
        0.72,
        annotated,
        0.28,
        0,
        annotated
    )

    cv2.putText(
        annotated,
        f"IN {in_count}   OUT {out_count}",
        (18, 34),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.50,
        (255, 255, 255),
        1
    )

    cv2.putText(
        annotated,
        f"INSIDE {occupancy}",
        (18, 59),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.50,
        (255, 255, 255),
        1
    )

    cv2.putText(
        annotated,
        f"LAST {last_event_text} {last_event_clock}",
        (18, 83),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.40,
        (255, 255, 255),
        1
    )

    cv2.putText(
        annotated,
        current_day.isoformat(),
        (18, 104),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.32,
        (185, 185, 185),
        1
    )

    if HEADLESS:
        key = 255
    else:
        cv2.imshow("LAB VISITOR COUNTER", annotated)
        key = cv2.waitKey(1) & 0xFF

    if key == 27:
        break

    if key == ord("i"):
        invert_direction = not invert_direction
        save_config(p1, p2, invert_direction)
        print("ARAH IN / OUT DIBALIK")

    if key == ord("r"):
        p1, p2 = select_line(frame)
        tracks.clear()
        save_config(p1, p2, invert_direction)
        print("GARIS DISET ULANG")

    if key == ord("c"):
        clear_today_test_data()
        in_count = 0
        out_count = 0
        occupancy = 0
        last_event_text = "-"
        last_event_clock = ""
        tracks.clear()
        print("DATA TEST HARI INI DIHAPUS. COUNTER = 0")


cap.release()
cv2.destroyAllWindows()
HEARTBEAT_FILE.unlink(missing_ok=True)

print("Visitor counter dihentikan.")
