import hmac
import os

from fastapi import Header, HTTPException


DEFAULT_DEVICE_ID = "lab-robotika-01"


def configured_device_id() -> str:
    return os.getenv("LABHUB_EDGE_DEVICE_ID", DEFAULT_DEVICE_ID).strip() or DEFAULT_DEVICE_ID


def require_edge_device(
    x_labhub_device: str = Header(default=""),
    x_labhub_device_token: str = Header(default=""),
) -> str:
    expected_device = configured_device_id()
    expected_token = os.getenv("LABHUB_EDGE_DEVICE_TOKEN", "")

    if len(expected_token) < 24:
        raise HTTPException(status_code=503, detail="Edge device token belum dikonfigurasi")
    if not hmac.compare_digest(x_labhub_device, expected_device):
        raise HTTPException(status_code=401, detail="Device tidak dikenal")
    if not hmac.compare_digest(x_labhub_device_token, expected_token):
        raise HTTPException(status_code=401, detail="Token device tidak valid")
    return x_labhub_device
