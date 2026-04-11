import cv2
import numpy as np
import time
from ultralytics import YOLO
import torch

def run_test():
    print(f"CUDA Available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"Device: {torch.cuda.get_device_name(0)}")
        
    print("Loading TensorRT Engine...")
    model = YOLO("models/yolov8n-pose.engine", task="pose")
    
    # Create dummy frame
    dummy_frame = np.zeros((640, 640, 3), dtype=np.uint8)
    
    print("Warming up GPU...")
    for _ in range(10):
        model.predict(dummy_frame, device="cuda", half=True, verbose=False)
        
    print("Starting exact 100-frame benchmark...")
    start_time = time.time()
    
    for _ in range(100):
        model.predict(dummy_frame, device="cuda", half=True, verbose=False)
        
    end_time = time.time()
    
    total_time = end_time - start_time
    fps = 100 / total_time
    print("-" * 30)
    print(f"BENCHMARK COMPLETED")
    print(f"Total Time (100 frames): {total_time:.3f} seconds")
    print(f"Average FPS: {fps:.2f} frames per second")
    print(f"Latency per frame: {(total_time/100)*1000:.2f} ms")
    print("-" * 30)

if __name__ == "__main__":
    run_test()
