import time, cv2, numpy as np, torch, logging, os
logging.getLogger().setLevel(logging.ERROR)

os.environ["MODEL_DEVICE"] = "cpu"
os.environ["CUDA_VISIBLE_DEVICES"] = ""

from core.detector import Detector

d = Detector()
frame = cv2.imread("data/latest_frame.jpg")
if frame is None: frame = np.zeros((480, 640, 3), dtype=np.uint8)
else: frame = cv2.resize(frame, (640, 480))

print("Warming up CPU model...")
for _ in range(5): d.detect(frame)

n = 50
print(f"Running CPU benchmark...")
t0 = time.time()
for _ in range(n): d.detect(frame)
t1 = time.time()

print(f"=============================")
print(f"--- CPU Benchmark Results ---")
print(f"Average latency: {(t1 - t0) * 1000 / n:.2f} ms")
print(f"Throughput: {n / (t1 - t0):.2f} FPS")
print(f"=============================")
