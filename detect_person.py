import os
import cv2
from getpass import getpass
from urllib.parse import quote
from ultralytics import YOLO

CAMERA_IP = "192.168.137.95"

# RTSP pakai TCP
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

# Minta password CCTV tanpa menampilkannya
password = getpass("Password C6N: ")
password = quote(password, safe="")

rtsp_url = f"rtsp://admin:{password}@{CAMERA_IP}:554/ch1/main"

print("Loading model...")

# Model kecil supaya ringan untuk realtime
model = YOLO("yolo26n.pt")

print("Menghubungkan ke CCTV...")

cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)

if not cap.isOpened():
    print("GAGAL membuka CCTV")
    raise SystemExit

print("BERHASIL!")
print("Tekan Q untuk keluar.")

while True:
    ret, frame = cap.read()

    if not ret:
        print("Gagal membaca frame.")
        break

    # Deteksi object
    results = model(
        frame,
        classes=[0],     # hanya PERSON
        conf=0.40,
        verbose=False
    )

    # Gambar bounding box hasil deteksi
    annotated_frame = results[0].plot()

    cv2.imshow(
        "EZVIZ C6N - Person Detection",
        annotated_frame
    )

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()