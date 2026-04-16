"""
scripts/demo_simulation.py — End-to-end SafeSphere simulation.

Simulates the full lifecycle:
  1. Registers 2 cameras with the coordinator.
  2. Creates a user and starts a journey.
  3. Sends GPS pings (simulating mobile app).
  4. Posts synthetic threat alerts (simulating edge AI).
  5. Triggers a blind-spot delay anomaly.
  6. Shows how alerts propagate to all stakeholders.

Run:
    1. Start coordinator:  uvicorn coordinator.main:app --port 8000
    2. Start dashboard:    cd dashboard && npm run dev
    3. Run simulation:     python -m scripts.demo_simulation
"""

import json
import time
import argparse
import requests


def run_demo(base_url: str, delay: float = 2.0):
    print("\n" + "═" * 60)
    print("  🛡️  SafeSphere End-to-End Simulation")
    print("═" * 60)

    headers = {}

    # ── Step 1: Register cameras ──────────────────────────────────────────────
    print("\n📷 Step 1: Registering edge cameras…")
    cam_ids = []
    cameras = [
        {"name": "Cam-1: Gate A", "latitude": 22.5535, "longitude": 88.3512,
         "coverage_radius_m": 40.0},
        {"name": "Cam-2: Gate B", "latitude": 22.5540, "longitude": 88.3520,
         "coverage_radius_m": 40.0},
    ]
    for cam in cameras:
        resp = requests.post(f"{base_url}/api/v1/cameras/register", json=cam)
        if resp.status_code == 201:
            cid = resp.json()["id"]
            cam_ids.append(cid)
            print(f"  ✅ {cam['name']} → {cid[:8]}")
        else:
            print(f"  ❌ {cam['name']}: {resp.status_code}")
            cam_ids.append(None)

    time.sleep(delay)

    # ── Step 2: Create user & login ──────────────────────────────────────────
    print("\n👤 Step 2: Creating user & logging in…")
    user_data = {
        "email": "simuser@safesphere.dev",
        "name": "Simulation User",
        "phone": "+919123456789",
        "password": "sim-password-123",
    }
    resp = requests.post(f"{base_url}/api/v1/auth/register", json=user_data)
    if resp.status_code in (201, 409):
        print(f"  ✅ User ready: {user_data['email']}")
    else:
        print(f"  ❌ Registration failed: {resp.status_code}")

    login_resp = requests.post(f"{base_url}/api/v1/auth/login", json={
        "email": user_data["email"],
        "password": user_data["password"],
    })
    if login_resp.status_code == 200:
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print(f"  ✅ Logged in, token acquired")
    else:
        print(f"  ❌ Login failed: {login_resp.status_code}")
        return

    # ── Step 3: Add family contact ───────────────────────────────────────────
    print("\n👨‍👩‍👧 Step 3: Adding family contact…")
    family = {
        "name": "Emergency Contact",
        "phone": "+919876543210",
        "email": "family@example.com",
        "relationship_label": "Parent",
        "notify_on_journey": True,
    }
    resp = requests.post(f"{base_url}/api/v1/auth/family", json=family, headers=headers)
    if resp.status_code == 201:
        print(f"  ✅ Added: {family['name']}")
    else:
        print(f"  ⚠ {resp.status_code} (may already exist)")

    time.sleep(delay)

    # ── Step 4: Create & start journey ───────────────────────────────────────
    print("\n🗺️ Step 4: Creating journey…")
    journey = {
        "start_lat": 22.5535,
        "start_lng": 88.3512,
        "end_lat": 22.5548,
        "end_lng": 88.3530,
        "start_address": "Park Street Entrance",
        "end_address": "Camac Street Junction",
    }
    resp = requests.post(f"{base_url}/api/v1/journey", json=journey, headers=headers)
    if resp.status_code != 201:
        print(f"  ❌ Journey creation failed: {resp.status_code}")
        return
    journey_id = resp.json()["id"]
    print(f"  ✅ Journey created: {journey_id[:8]}")

    # Start the journey
    resp = requests.patch(
        f"{base_url}/api/v1/journey/{journey_id}",
        json={"status": "active"},
        headers=headers,
    )
    print(f"  ✅ Journey STARTED")

    time.sleep(delay)

    # ── Step 5: Simulate GPS pings ───────────────────────────────────────────
    print("\n📍 Step 5: Sending GPS pings (simulating mobile movement)…")
    gps_path = [
        (22.5536, 88.3513),
        (22.5537, 88.3515),
        (22.5538, 88.3517),
        (22.5539, 88.3519),
    ]
    for i, (lat, lng) in enumerate(gps_path):
        resp = requests.post(
            f"{base_url}/api/v1/journey/{journey_id}/gps",
            json={"latitude": lat, "longitude": lng, "speed_mps": 1.3},
            headers=headers,
        )
        print(f"  📍 Ping {i+1}: ({lat}, {lng}) → {resp.json().get('status', 'error')}")
        time.sleep(delay * 0.5)

    # ── Step 6: Simulate threat escalation ───────────────────────────────────
    print("\n⚠️ Step 6: Simulating threat escalation…")

    threat_sequence = [
        {"level": "LOW", "score": 0.38, "type": "threat", "msg": "Person approaching"},
        {"level": "MEDIUM", "score": 0.62, "type": "threat", "msg": "Sustained proximity + approach"},
        {"level": "HIGH", "score": 0.85, "type": "threat", "msg": "Encirclement detected!"},
    ]

    for threat in threat_sequence:
        alert_body = {
            "camera_id": cam_ids[0] if cam_ids[0] else None,
            "journey_id": journey_id,
            "track_id": 42,
            "threat_level": threat["level"],
            "threat_score": threat["score"],
            "latitude": 22.5538,
            "longitude": 88.3516,
            "location_name": "Park Street corridor",
            "alert_type": threat["type"],
            "details": json.dumps({"description": threat["msg"]}),
        }
        resp = requests.post(f"{base_url}/api/v1/alerts", json=alert_body)
        if resp.status_code == 201:
            alert = resp.json()
            emoji = {"LOW": "🟡", "MEDIUM": "🟠", "HIGH": "🔴"}
            print(f"  {emoji.get(threat['level'], '⚪')} {threat['level']}: {threat['msg']}")
            print(f"     → User notified: {alert.get('notified_user')}")
            print(f"     → Family notified: {alert.get('notified_family')}")
            print(f"     → Security notified: {alert.get('notified_security')}")
        else:
            print(f"  ❌ Alert failed: {resp.status_code}")
        time.sleep(delay)

    # ── Step 7: Simulate blind-spot anomaly ──────────────────────────────────
    print("\n👻 Step 7: Simulating blind-spot anomaly…")
    blind_spot = {
        "camera_id": cam_ids[0] if cam_ids[0] else None,
        "journey_id": journey_id,
        "track_id": 42,
        "threat_level": "MEDIUM",
        "threat_score": 0.65,
        "latitude": 22.5538,
        "longitude": 88.3516,
        "location_name": "Between Gate A and Gate B",
        "alert_type": "blind_spot",
        "details": json.dumps({
            "description": "Person delayed between cameras — exceeded transit window",
            "expected_transit_s": 70,
            "actual_delay_s": 95,
        }),
    }
    resp = requests.post(f"{base_url}/api/v1/alerts", json=blind_spot)
    if resp.status_code == 201:
        print(f"  👻 Blind-spot alert raised! Person delayed between cameras")
    else:
        print(f"  ❌ {resp.status_code}")

    time.sleep(delay)

    # ── Step 8: Complete journey ─────────────────────────────────────────────
    print("\n✅ Step 8: Completing journey…")
    resp = requests.patch(
        f"{base_url}/api/v1/journey/{journey_id}",
        json={"status": "completed"},
        headers=headers,
    )
    print(f"  ✅ Journey COMPLETED")

    # ── Summary ──────────────────────────────────────────────────────────────
    print("\n" + "═" * 60)
    print("  🛡️  Simulation Complete!")
    print("═" * 60)
    print(f"  Cameras registered: {len([c for c in cam_ids if c])}")
    print(f"  GPS pings sent: {len(gps_path)}")
    print(f"  Threat alerts: {len(threat_sequence)}")
    print(f"  Blind-spot anomaly: 1")
    print(f"\n  📊 View results:")
    print(f"     Dashboard: http://localhost:5173")
    print(f"     API docs:  {base_url}/docs")
    print(f"     Alerts:    {base_url}/api/v1/alerts")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SafeSphere E2E simulation")
    parser.add_argument("--url", default="http://localhost:8000", help="Coordinator URL")
    parser.add_argument("--delay", type=float, default=1.5, help="Delay between steps (seconds)")
    args = parser.parse_args()
    run_demo(args.url, args.delay)
