"""
scripts/launch_dual_nodes.py — SafeSphere Dual-Node Launcher.

This script launches the Coordinator and two independent AI Threat Engines,
each pointing to a different phone IP camera stream.

Usage:
    python scripts/launch_dual_nodes.py http://IP_PHONE_1:8080/video http://IP_PHONE_2:8080/video
"""

import subprocess
import sys
import time
import signal
import os

def main():
    if len(sys.argv) < 3:
        print("Usage: python scripts/launch_dual_nodes.py <URL_PHONE_1> <URL_PHONE_2>")
        print("Example: python scripts/launch_dual_nodes.py http://192.168.1.5:8080/video http://192.168.1.6:8080/video")
        sys.exit(1)

    url1 = sys.argv[1]
    url2 = sys.argv[2]

    processes = []

    try:
        print("🚀 [1/3] Starting SafeSphere Coordinator Hub...")
        p_coord = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "coordinator.main:app", "--host", "0.0.0.0", "--port", "8000"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT
        )
        processes.append(p_coord)
        time.sleep(3)  # Wait for DB init

        print(f"👁️ [2/3] Starting NODE_01 (Phone 1) -> {url1}")
        p_node1 = subprocess.Popen([
            sys.executable, "main.py",
            "--source", url1,
            "--cam-id", "phone_node_01",
            "--cam-name", "Guardian Phone Alpha",
            "--no-display"
        ])
        processes.append(p_node1)

        print(f"👁️ [3/3] Starting NODE_02 (Phone 2) -> {url2}")
        p_node2 = subprocess.Popen([
            sys.executable, "main.py",
            "--source", url2,
            "--cam-id", "phone_node_02",
            "--cam-name", "Guardian Phone Beta",
            "--no-display"
        ])
        processes.append(p_node2)

        print("\n✅ SYSTEM ONLINE: Obsidian Cluster synchronized.")
        print("Access Dashboard at http://localhost:5173")
        print("Press Ctrl+C to terminate the cluster.")

        while True:
            # Check if processes are still running
            for i, p in enumerate(processes):
                if p.poll() is not None:
                    # process finished/crashed
                    name = "COORDINATOR" if i == 0 else f"NODE_0{i}"
                    print(f"\n⚠️  [CRITICAL] {name} has stopped (Exit Code: {p.returncode})")
                    print("Check logs/camera.log for details.")
                    raise KeyboardInterrupt
            time.sleep(2)

    except KeyboardInterrupt:
        print("\n🛑 Shutting down cluster...")
        for p in processes:
            p.terminate()
            p.wait()
        print("System offline.")

if __name__ == "__main__":
    main()
