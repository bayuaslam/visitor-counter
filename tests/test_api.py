import os
from datetime import datetime, timedelta, timezone

import api_server


EDGE_HEADERS = {
    "X-LabHub-Device": "lab-robotika-01",
    "X-LabHub-Device-Token": "test-edge-device-token-0123456789-abcdef",
}
STUDENT_HEADERS = {
    "Content-Type": "application/json",
    "X-LabHub-Role": "STUDENT",
    "X-LabHub-User": "student.demo",
    "X-LabHub-Name": "Mahasiswa Demo",
}
LABORAN_HEADERS = {
    "Content-Type": "application/json",
    "X-LabHub-Role": "LABORAN",
    "X-LabHub-User": "laboran.demo",
    "X-LabHub-Name": "Laboran Demo",
}


def test_health_and_security_headers(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'self'" in response.headers["content-security-policy"]


def test_guest_can_browse_but_cannot_submit_request(client):
    guest = client.post("/api/auth/guest")
    assert guest.status_code == 200
    assert guest.json()["guest"] is True

    requests = client.get("/api/requests", headers=STUDENT_HEADERS)
    assert requests.status_code == 200
    assert requests.json() == []

    create = client.post(
        "/api/requests",
        headers=STUDENT_HEADERS,
        json={
            "request_type": "ROOM_BOOKING",
            "title": "Tes booking",
            "room_name": "Lab Utama",
            "start_at": "2026-08-12T10:00:00",
            "end_at": "2026-08-12T11:00:00",
            "quantity": 1,
            "details": {"participants": 2},
        },
    )
    assert create.status_code == 403


def test_registration_requires_email_code(client, monkeypatch):
    sent = {}

    def fake_send(email, code):
        sent["email"] = email
        sent["code"] = code

    monkeypatch.setattr(api_server, "send_verification_email", fake_send)

    start = client.post(
        "/api/auth/register",
        json={"email": "mahasiswa@uii.ac.id", "password": "password-kuat-123"},
    )
    assert start.status_code == 202
    assert start.json()["verification_required"] is True
    assert sent["email"] == "mahasiswa@uii.ac.id"
    assert len(sent["code"]) == 6

    wrong = client.post(
        "/api/auth/register/verify",
        json={"email": "mahasiswa@uii.ac.id", "code": "000000" if sent["code"] != "000000" else "111111"},
    )
    assert wrong.status_code == 400

    verified = client.post(
        "/api/auth/register/verify",
        json={"email": "mahasiswa@uii.ac.id", "code": sent["code"]},
    )
    assert verified.status_code == 201
    assert verified.json()["authenticated"] is True

    session = client.get("/api/auth/session")
    assert session.status_code == 200
    assert session.json()["email"] == "mahasiswa@uii.ac.id"


def test_edge_requires_valid_token(client):
    response = client.post(
        "/api/edge/heartbeat",
        headers={"X-LabHub-Device": "lab-robotika-01", "X-LabHub-Device-Token": "wrong-token"},
        json={"occupancy": 0},
    )
    assert response.status_code == 401


def test_edge_event_sync_is_idempotent_and_updates_dashboard(client):
    heartbeat = client.post(
        "/api/edge/heartbeat",
        headers=EDGE_HEADERS,
        json={
            "camera_ip": "192.168.137.88",
            "stream": "ch1/sub",
            "mode": "Background",
            "occupancy": 1,
            "counter_active": True,
        },
    )
    assert heartbeat.status_code == 200

    status = client.get("/api/counter/status")
    assert status.status_code == 200
    assert status.json()["edge_connected"] is True
    assert status.json()["active"] is True

    occurred = datetime.now(timezone(timedelta(hours=7))).replace(microsecond=0).isoformat()
    payload = {
        "events": [
            {
                "event_uuid": "edge-event-00000001",
                "timestamp": occurred,
                "track_id": 42,
                "direction": "IN",
                "occupancy_after": 1,
            }
        ]
    }

    first = client.post("/api/edge/events", headers=EDGE_HEADERS, json=payload)
    assert first.status_code == 200
    assert first.json() == {"accepted": 1, "duplicates": 0}

    duplicate = client.post("/api/edge/events", headers=EDGE_HEADERS, json=payload)
    assert duplicate.status_code == 200
    assert duplicate.json() == {"accepted": 0, "duplicates": 1}

    summary = client.get("/api/visitors")
    assert summary.status_code == 200
    assert summary.json()["today_in"] == 1
    assert summary.json()["inside"] == 1

    recent = client.get("/api/visitors/recent?limit=5")
    assert recent.status_code == 200
    assert recent.json()["events"][0]["direction"] == "IN"

    stopped = client.post(
        "/api/edge/heartbeat",
        headers=EDGE_HEADERS,
        json={"occupancy": 1, "counter_active": False},
    )
    assert stopped.status_code == 200
    stopped_status = client.get("/api/counter/status").json()
    assert stopped_status["edge_connected"] is True
    assert stopped_status["active"] is False


def test_admin_reset_queues_edge_command(client):
    password = "admin-password-12345"
    os.environ["LABHUB_ADMIN_PASSWORD_HASH"] = api_server.hash_password(password)

    login = client.post("/api/admin/login", json={"password": password})
    assert login.status_code == 200

    reset = client.post("/api/admin/counter/reset", headers=LABORAN_HEADERS)
    assert reset.status_code == 200
    assert reset.json()["inside"] == 0

    commands = client.get("/api/edge/commands", headers=EDGE_HEADERS)
    assert commands.status_code == 200
    assert commands.json()["commands"][0]["command"] == "RESET_COUNTER"

    command_id = commands.json()["commands"][0]["id"]
    ack = client.post(f"/api/edge/commands/{command_id}/ack", headers=EDGE_HEADERS, json={})
    assert ack.status_code == 200

    after = client.get("/api/edge/commands", headers=EDGE_HEADERS)
    assert after.json()["commands"] == []
