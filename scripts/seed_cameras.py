"""
scripts/seed_cameras.py — Seed the coordinator with 2-4 camera nodes for demonstration.

Run:
    python -m scripts.seed_cameras --url http://localhost:8000

Creates camera nodes at predefined GPS positions with blind-spot links.
"""

import argparse
import requests
import sys
import json


# ── Predefined camera positions (Kolkata area for demo) ─────────────────────

CAMERAS = [
    {
        "name": "Cam-A: Park Street Entrance",
        "latitude": 22.5535,
        "longitude": 88.3512,
        "coverage_radius_m": 40.0,
        "source_url": "rtsp://cam-a/stream",
    },
    {
        "name": "Cam-B: Park Street Mid-block",
        "latitude": 22.5540,
        "longitude": 88.3520,
        "coverage_radius_m": 40.0,
        "source_url": "rtsp://cam-b/stream",
    },
    {
        "name": "Cam-C: Camac St Junction",
        "latitude": 22.5548,
        "longitude": 88.3530,
        "coverage_radius_m": 50.0,
        "source_url": "rtsp://cam-c/stream",
    },
    {
        "name": "Cam-D: AJC Bose Road",
        "latitude": 22.5525,
        "longitude": 88.3505,
        "coverage_radius_m": 45.0,
        "source_url": "rtsp://cam-d/stream",
    },
]

# Blind-spot links: pairs of cameras with walking distance between them
LINKS = [
    {"from_idx": 0, "to_idx": 1, "distance_m": 95},
    {"from_idx": 1, "to_idx": 2, "distance_m": 120},
    {"from_idx": 0, "to_idx": 3, "distance_m": 80},
]


def seed(base_url: str):
    print(f"\n🌐 Seeding cameras into {base_url}")
    print("=" * 60)

    registered = []

    for cam in CAMERAS:
        try:
            resp = requests.post(f"{base_url}/api/v1/cameras/register", json=cam, timeout=5)
            if resp.status_code == 201:
                data = resp.json()
                registered.append(data)
                print(f"  ✅ Registered: {data['name']} (ID: {data['id'][:8]})")
            else:
                print(f"  ❌ Failed: {cam['name']} — {resp.status_code}: {resp.text[:100]}")
                registered.append(None)
        except Exception as e:
            print(f"  ❌ Error: {cam['name']} — {e}")
            registered.append(None)

    # ── Create blind-spot links ───────────────────────────────────────────────
    print(f"\n🔗 Creating blind-spot links")
    print("-" * 40)

    for link in LINKS:
        cam_from = registered[link["from_idx"]]
        cam_to = registered[link["to_idx"]]
        if not cam_from or not cam_to:
            print(f"  ⚠ Skipping link {link['from_idx']}→{link['to_idx']} (missing camera)")
            continue

        print(f"  🔗 {cam_from['name'][:20]} → {cam_to['name'][:20]} ({link['distance_m']}m)")
        # Note: In a full implementation, we'd have a separate endpoint for links.
        # For now, this is documented as metadata.

    # ── Create a demo user ─────────────────────────────────────────────────────
    print(f"\n👤 Creating demo user")
    print("-" * 40)

    demo_user = {
        "email": "demo@safesphere.dev",
        "name": "Demo User",
        "phone": "+919876543210",
        "password": "safesphere-demo-2026",
    }
    try:
        resp = requests.post(f"{base_url}/api/v1/auth/register", json=demo_user, timeout=5)
        if resp.status_code == 201:
            user = resp.json()
            print(f"  ✅ User: {user['email']} (ID: {user['id'][:8]})")
        elif resp.status_code == 409:
            print(f"  ℹ User already exists: {demo_user['email']}")
        else:
            print(f"  ❌ Failed: {resp.status_code}: {resp.text[:100]}")
    except Exception as e:
        print(f"  ❌ Error: {e}")

    # ── Add family contact ────────────────────────────────────────────────────
    print(f"\n👨‍👩‍👧 Adding family contact")
    print("-" * 40)

    try:
        login_resp = requests.post(
            f"{base_url}/api/v1/auth/login",
            json={"email": demo_user["email"], "password": demo_user["password"]},
            timeout=5,
        )
        if login_resp.status_code == 200:
            token = login_resp.json()["access_token"]
            family = {
                "name": "Mom",
                "phone": "+919876543211",
                "email": "parent@example.com",
                "relationship_label": "Mother",
                "notify_on_journey": True,
            }
            fam_resp = requests.post(
                f"{base_url}/api/v1/auth/family",
                json=family,
                headers={"Authorization": f"Bearer {token}"},
                timeout=5,
            )
            if fam_resp.status_code == 201:
                print(f"  ✅ Added: {family['name']} ({family['relationship_label']})")
            else:
                print(f"  ❌ Failed: {fam_resp.status_code}")
    except Exception as e:
        print(f"  ❌ Error: {e}")

    print(f"\n{'=' * 60}")
    print(f"✅ Seeding complete: {sum(1 for r in registered if r)} cameras registered")
    print(f"   Coordinator: {base_url}")
    print(f"   Dashboard: http://localhost:5173")
    print(f"   API docs: {base_url}/docs")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed SafeSphere coordinator")
    parser.add_argument("--url", default="http://localhost:8000", help="Coordinator URL")
    args = parser.parse_args()
    seed(args.url)
