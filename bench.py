import time
import cv2
import numpy as np
import torch
from core.detector import Detector
import logging

# Suppress logs
logging.getLogger().setLevel(logging.ERROR)

print(f"CUDA Available: {torch.cuda.is_available()}")
d = Detector()

frame = cv2.imread("data/latest_frame.jpg")
if frame is None:
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
else:
    frame = cv2.resize(frame, (640, 480))

print("Warming up...")
for _ in range(5): 
    d.detect(frame)

n = 50
print(f"Running benchmark on {n} frames...")
t0 = time.time()
for _ in range(n):
    d.detect(frame)
t1 = time.time()

avg_lat = (t1 - t0) * 1000 / n
fps = n / (t1 - t0)

print(f"=============================")
print(f"--- GPU Benchmark Results ---")
print(f"Frames: {n}")
print(f"Total time: {t1-t0:.2f} s")
print(f"Average latency: {avg_lat:.2f} ms")
print(f"Throughput: {fps:.2f} FPS")
print(f"=============================")
