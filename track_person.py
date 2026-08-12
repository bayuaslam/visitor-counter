import os
import csv
import cv2
from datetime import datetime
from getpass import getpass
from urllib.parse import quote
from ultralytics import YOLO

CAMERA_IP = "192.168.137.95"

# RTSP lewat TCP
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

# Folder screenshot
CAPTURE_FOLDER = "captures"
os.makedirs(CAPTURE_FOLDER, exist_ok=True)

# File log
LOG_FILE = "detection_log.csv"

# Buat header CSV kalau file belum ada
if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["time", "track_id", "confidence", "image"])

# Password CCTV
password = getpass("Password C6N: ")
password = quote(password, safe="")

rtsp_url = (
    f"rtsp://admin:{password}"
    f"@{CAMERA_IP}:554/ch1/main"
)

# Load YOLO
print("Loading YOLO...")
model = YOLO("yolo26n.pt")

print("Menghubungkan ke CCTV...")

cap = cv2.VideoCapture(
    rtsp_url,
    cv2.CAP_FFMPEG
)

if not cap.isOpened():
    print("GAGAL membuka CCTV")
    raise SystemExit

print("")
print("==============================")
print(" TRACKING SUDAH AKTIF")
print("==============================")
print("Tinggalin PC dan jalan ke depan CCTV.")
print("Screenshot akan tersimpan otomatis.")
print("Tekan ESC untuk keluar.")
print("")

# Menyimpan ID yang sudah pernah kita capture
seen_ids = set()

while True:

    ret, frame = cap.read()

    if not ret:
        print("Gagal membaca frame")
        continue

    # Tracking
    results = model.track(
        frame,
        persist=True,
        tracker="bytetrack.yaml",
        classes=[0],      # person saja
        conf=0.25,
        imgsz=640,
        verbose=False
    )

    result = results[0]

    annotated = frame.copy()

    person_count = 0

    if result.boxes is not None:

        for box in result.boxes:

            cls_id = int(box.cls[0].item())

            # Hanya manusia
            if cls_id != 0:
                continue

            person_count += 1

            confidence = float(
                box.conf[0].item()
            )

            x1, y1, x2, y2 = map(
                int,
                box.xyxy[0].tolist()
            )

            # Belum punya tracking ID
            if box.id is None:
                track_id = None
                label = f"Person {confidence:.2f}"

            else:
                track_id = int(
                    box.id[0].item()
                )

                label = (
                    f"Person #{track_id} "
                    f"{confidence:.2f}"
                )

            # Gambar bounding box
            cv2.rectangle(
                annotated,
                (x1, y1),
                (x2, y2),
                (0, 255, 0),
                2
            )

            cv2.putText(
                annotated,
                label,
                (x1, max(25, y1 - 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2
            )

            # Kalau ID baru terdeteksi
            if (
                track_id is not None
                and track_id not in seen_ids
            ):

                seen_ids.add(track_id)

                now = datetime.now()

                timestamp_file = now.strftime(
                    "%Y-%m-%d_%H-%M-%S"
                )

                timestamp_log = now.strftime(
                    "%Y-%m-%d %H:%M:%S"
                )

                filename = (
                    f"person_{track_id}_"
                    f"{timestamp_file}.jpg"
                )

                filepath = os.path.join(
                    CAPTURE_FOLDER,
                    filename
                )

                # Screenshot frame lengkap
                cv2.imwrite(
                    filepath,
                    annotated
                )

                # Simpan ke CSV
                with open(
                    LOG_FILE,
                    "a",
                    newline="",
                    encoding="utf-8"
                ) as f:

                    writer = csv.writer(f)

                    writer.writerow([
                        timestamp_log,
                        track_id,
                        round(confidence, 3),
                        filepath
                    ])

                print(
                    f"[{timestamp_log}] "
                    f"PERSON #{track_id} "
                    f"DETECTED "
                    f"confidence={confidence:.2f}"
                )

    # Counter layar
    cv2.putText(
        annotated,
        f"PERSON: {person_count}",
        (20, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (255, 255, 255),
        2
    )

    cv2.imshow(
        "C6N - Person Tracking",
        annotated
    )

    key = cv2.waitKey(1) & 0xFF

    if key == 27:  # ESC
        break

cap.release()
cv2.destroyAllWindows()

print("Program dihentikan.")