import cv2
import sys
import time

def test_cam(url):
    print(f"--- Testing connection to: {url} ---")
    cap = cv2.VideoCapture(url)
    
    if not cap.isOpened():
        print("FAIL: Could not open video stream.")
        return
    
    print("SUCCESS: Stream opened. Capturing sample frame...")
    ret, frame = cap.read()
    if ret:
        print(f"SUCCESS: Captured frame of size {frame.shape[1]}x{frame.shape[0]}")
    else:
        print("FAIL: Could not read frame from stream.")
    
    cap.release()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python camera_diag.py <URL>")
        sys.exit(1)
    test_cam(sys.argv[1])
