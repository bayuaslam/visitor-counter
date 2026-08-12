import json
import os
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import quote

import cv2


APP_DIR = Path(r"C:\visitor-counter")
CAMERA_MAC = "64-24-4d-81-4f-08"


def find_camera_ip():
    target = CAMERA_MAC.lower()
    arp = subprocess.run(["arp.exe", "-a"], capture_output=True, text=True, timeout=10).stdout
    for line in arp.splitlines():
        match = re.search(r"\b(\d{1,3}(?:\.\d{1,3}){3})\s+([0-9a-fA-F-]{17})\b", line)
        if match and match.group(2).lower() == target:
            return match.group(1)
    raise RuntimeError("Kamera EZVIZ belum ditemukan di jaringan Ethernet.")


def load_password():
    decrypt_script = r"""
$encrypted = (Get-Content -Raw -LiteralPath 'C:\visitor-counter\camera_password.dpapi').Trim()
$secure = ConvertTo-SecureString $encrypted
$pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try { [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
"""
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", decrypt_script],
        capture_output=True,
        text=True,
        timeout=10,
    )
    password = result.stdout.strip()
    if result.returncode != 0 or not password:
        raise RuntimeError("Kredensial kamera tidak dapat dibuka oleh akun Windows ini.")
    return password


def connect():
    ip = find_camera_ip()
    password = quote(load_password(), safe="")
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
    stream = cv2.VideoCapture(f"rtsp://admin:{password}@{ip}:554/ch1/sub", cv2.CAP_FFMPEG)
    stream.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if not stream.isOpened():
        raise RuntimeError(f"Stream kamera {ip} tidak dapat dibuka.")
    return ip, stream


def main():
    config = json.loads((APP_DIR / "line_config.json").read_text(encoding="utf-8"))
    p1, p2 = tuple(config["p1"]), tuple(config["p2"])
    camera_ip, stream = connect()
    window = "PREVIEW KAMERA SMARTLAB - ESC / Q untuk keluar"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)

    missed_frames = 0
    while True:
        ok, frame = stream.read()
        if not ok:
            missed_frames += 1
            if missed_frames > 60:
                stream.release()
                time.sleep(1)
                camera_ip, stream = connect()
                missed_frames = 0
            continue

        missed_frames = 0
        cv2.line(frame, p1, p2, (0, 255, 255), 2)
        cv2.circle(frame, p1, 4, (0, 180, 255), -1)
        cv2.circle(frame, p2, 4, (0, 180, 255), -1)
        cv2.rectangle(frame, (8, 8), (244, 58), (18, 36, 29), -1)
        cv2.putText(frame, f"CAMERA {camera_ip}", (18, 29), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 255, 255), 1)
        cv2.putText(frame, "GARIS KUNING = BATAS COUNTER", (18, 49), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 255, 255), 1)
        cv2.imshow(window, frame)

        key = cv2.waitKey(1) & 0xFF
        if key in (27, ord("q"), ord("Q")):
            break

    stream.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Preview gagal: {error}")
        input("Tekan Enter untuk menutup...")
