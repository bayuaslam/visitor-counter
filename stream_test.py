import os
import cv2
from getpass import getpass
from urllib.parse import quote

CAMERA_IP = "192.168.137.95"

# Paksa RTSP lewat TCP supaya biasanya lebih stabil
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

password = getpass("Masukkan password/verification code C6N: ")
password = quote(password, safe="")

rtsp_url = f"rtsp://admin:{password}@{CAMERA_IP}:554/ch1/main"

print("Menghubungkan ke C6N...")

cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)

if not cap.isOpened():
    print("GAGAL membuka stream.")
    print("Cek IP, password, atau RTSP C6N.")
    raise SystemExit

print("BERHASIL! Tekan Q untuk keluar.")

while True:
    ret, frame = cap.read()

    if not ret:
        print("Gagal membaca frame.")
        break

    cv2.imshow("EZVIZ C6N - Visitor Counter", frame)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()