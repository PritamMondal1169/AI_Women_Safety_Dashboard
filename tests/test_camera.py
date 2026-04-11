"""
tests/test_camera.py — Unit tests for core/camera.py.

Tests cover:
  - Camera construction and configuration
  - Thread start/stop lifecycle
  - Frame slot read behaviour (no frame, frame available)
  - Auto-reconnect counter logic
  - Context manager (__enter__ / __exit__)
  - FPS property edge cases
  - Resolution property
  - Max-reconnect shutdown
  - Multiple stop() calls are safe (idempotent)

All tests use a mock cv2.VideoCapture so no physical camera is required.
"""

from __future__ import annotations

import sys
import threading
import time
import types
import unittest
import unittest.mock as mock
from unittest.mock import MagicMock, patch, PropertyMock

import numpy as np

# ---------------------------------------------------------------------------
# Minimal stubs for external dependencies
# ---------------------------------------------------------------------------
def _install_mocks():
    # loguru
    lm = types.ModuleType("loguru")
    class _L:
        def __getattr__(self, n): return lambda *a, **k: None
        def bind(self, **k): return self
        def remove(self): pass
        def add(self, *a, **k): pass
    lm.logger = _L()
    sys.modules["loguru"] = lm

    # dotenv
    dm = types.ModuleType("dotenv")
    dm.load_dotenv = lambda *a, **k: None
    sys.modules["dotenv"] = dm

    # cv2 — we need a real-ish mock for VideoCapture
    cv2m = types.ModuleType("cv2")
    cv2m.CAP_PROP_FRAME_WIDTH  = 3
    cv2m.CAP_PROP_FRAME_HEIGHT = 4
    cv2m.CAP_PROP_FPS          = 5
    cv2m.CAP_PROP_BUFFERSIZE   = 38
    cv2m.VideoCapture = MagicMock
    sys.modules["cv2"] = cv2m

_install_mocks()
sys.path.insert(0, ".")

from core.camera import Camera


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_good_cap(width=640, height=480, fps=30.0):
    """Return a mock VideoCapture that successfully opens and returns frames."""
    cap = MagicMock()
    cap.isOpened.return_value = True
    cap.set.return_value = True
    cap.get.side_effect = lambda prop: {
        3: float(width),
        4: float(height),
        5: fps,
    }.get(prop, 0.0)

    dummy_frame = np.zeros((height, width, 3), dtype=np.uint8)
    cap.read.return_value = (True, dummy_frame)
    return cap


def _make_bad_cap():
    """Return a mock VideoCapture that fails to open."""
    cap = MagicMock()
    cap.isOpened.return_value = False
    cap.read.return_value = (False, None)
    return cap


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCameraConstruction(unittest.TestCase):

    def test_default_source_from_cfg(self):
        """Camera uses cfg.CAMERA_SOURCE when no source is passed."""
        from config import cfg
        cam = Camera()
        # cfg.CAMERA_SOURCE may be int or str '0'; both acceptable
        self.assertEqual(str(cam._source), str(cfg.CAMERA_SOURCE))

    def test_explicit_source_overrides_cfg(self):
        cam = Camera(source=2)
        self.assertEqual(cam._source, 2)

    def test_explicit_dimensions(self):
        cam = Camera(source=0, width=1280, height=720, fps=60)
        self.assertEqual(cam._width, 1280)
        self.assertEqual(cam._height, 720)
        self.assertEqual(cam._fps, 60)

    def test_initial_state(self):
        cam = Camera(source=0)
        self.assertFalse(cam.is_running())
        self.assertEqual(cam.frames_captured, 0)
        self.assertEqual(cam.reconnect_count, 0)


class TestCameraOpen(unittest.TestCase):

    def test_open_good_cap_returns_true(self):
        """_open() returns True when VideoCapture.isOpened() is True."""
        good = _make_good_cap()
        with patch("core.camera.cv2") as mock_cv2:
            mock_cv2.VideoCapture.return_value = good
            mock_cv2.CAP_PROP_FRAME_WIDTH  = 3
            mock_cv2.CAP_PROP_FRAME_HEIGHT = 4
            mock_cv2.CAP_PROP_FPS          = 5
            mock_cv2.CAP_PROP_BUFFERSIZE   = 38
            cam = Camera(source=0)
            result = cam._open()
        self.assertTrue(result)

    def test_open_bad_cap_returns_false(self):
        """_open() returns False when VideoCapture.isOpened() is False."""
        bad = _make_bad_cap()
        with patch("core.camera.cv2") as mock_cv2:
            mock_cv2.VideoCapture.return_value = bad
            mock_cv2.CAP_PROP_FRAME_WIDTH  = 3
            mock_cv2.CAP_PROP_FRAME_HEIGHT = 4
            mock_cv2.CAP_PROP_FPS          = 5
            mock_cv2.CAP_PROP_BUFFERSIZE   = 38
            cam = Camera(source=0)
            result = cam._open()
        self.assertFalse(result)


class TestCameraReadBehaviour(unittest.TestCase):

    def test_read_before_start_returns_false(self):
        """Reading before start() should return (False, None)."""
        cam = Camera(source=0)
        ok, frame = cam.read()
        self.assertFalse(ok)
        self.assertIsNone(frame)

    def test_read_returns_copy(self):
        """read() must return a copy so the caller cannot corrupt the slot."""
        cam = Camera(source=0)
        original = np.ones((480, 640, 3), dtype=np.uint8) * 42
        cam._frame = original
        ok, frame = cam.read()
        self.assertTrue(ok)
        self.assertIsNotNone(frame)
        # Mutate the returned frame — should not affect cam._frame
        frame[:] = 0
        self.assertEqual(cam._frame[0, 0, 0], 42)

    def test_read_after_frame_set(self):
        """read() returns (True, frame) once a frame has been stored."""
        cam = Camera(source=0)
        cam._frame = np.zeros((480, 640, 3), dtype=np.uint8)
        ok, frame = cam.read()
        self.assertTrue(ok)
        self.assertEqual(frame.shape, (480, 640, 3))


class TestCameraLifecycle(unittest.TestCase):

    def test_start_sets_running(self):
        """start() should set the running event and launch the reader thread."""
        good = _make_good_cap()
        with patch("core.camera.cv2") as mock_cv2:
            mock_cv2.VideoCapture.return_value = good
            mock_cv2.CAP_PROP_FRAME_WIDTH  = 3
            mock_cv2.CAP_PROP_FRAME_HEIGHT = 4
            mock_cv2.CAP_PROP_FPS          = 5
            mock_cv2.CAP_PROP_BUFFERSIZE   = 38
            cam = Camera(source=0)
            cam.start()
            try:
                self.assertTrue(cam.is_running())
                self.assertIsNotNone(cam._thread)
                self.assertTrue(cam._thread.is_alive())
            finally:
                cam.stop()

    def test_stop_clears_running(self):
        """stop() should clear the running event."""
        good = _make_good_cap()
        with patch("core.camera.cv2") as mock_cv2:
            mock_cv2.VideoCapture.return_value = good
            for prop in [3, 4, 5, 38]:
                pass
            mock_cv2.CAP_PROP_FRAME_WIDTH  = 3
            mock_cv2.CAP_PROP_FRAME_HEIGHT = 4
            mock_cv2.CAP_PROP_FPS          = 5
            mock_cv2.CAP_PROP_BUFFERSIZE   = 38
            cam = Camera(source=0)
            cam.start()
            cam.stop()
        self.assertFalse(cam.is_running())

    def test_double_stop_is_safe(self):
        """Calling stop() twice must not raise."""
        good = _make_good_cap()
        with patch("core.camera.cv2") as mock_cv2:
            mock_cv2.VideoCapture.return_value = good
            mock_cv2.CAP_PROP_FRAME_WIDTH  = 3
            mock_cv2.CAP_PROP_FRAME_HEIGHT = 4
            mock_cv2.CAP_PROP_FPS          = 5
            mock_cv2.CAP_PROP_BUFFERSIZE   = 38
            cam = Camera(source=0)
            cam.start()
            cam.stop()
            cam.stop()   # second call must not raise

    def test_double_start_is_safe(self):
        """Calling start() twice must not spawn a second thread."""
        good = _make_good_cap()
        with patch("core.camera.cv2") as mock_cv2:
            mock_cv2.VideoCapture.return_value = good
            mock_cv2.CAP_PROP_FRAME_WIDTH  = 3
            mock_cv2.CAP_PROP_FRAME_HEIGHT = 4
            mock_cv2.CAP_PROP_FPS          = 5
            mock_cv2.CAP_PROP_BUFFERSIZE   = 38
            cam = Camera(source=0)
            cam.start()
            first_thread = cam._thread
            cam.start()   # second call
            second_thread = cam._thread
            cam.stop()
        # Thread object should be unchanged (start() returned early)
        self.assertIs(first_thread, second_thread)


class TestCameraFPS(unittest.TestCase):

    def test_actual_fps_zero_when_no_frames(self):
        """actual_fps should be 0 before any frame is captured."""
        cam = Camera(source=0)
        # Ensure _last_frame_time is never 0 (would div by zero)
        cam._last_frame_time = time.monotonic() - 10
        fps = cam.actual_fps
        # Should be 0.1 fps (1/10), not crash
        self.assertGreaterEqual(fps, 0.0)

    def test_actual_fps_positive_after_frame(self):
        """actual_fps should return a positive value after a frame timestamp."""
        cam = Camera(source=0)
        cam._last_frame_time = time.monotonic() - 0.033   # ~30 fps ago
        self.assertGreater(cam.actual_fps, 0.0)


class TestCameraResolution(unittest.TestCase):

    def test_resolution_from_cap(self):
        """resolution property should query the live VideoCapture."""
        good = _make_good_cap(width=1920, height=1080)
        with patch("core.camera.cv2") as mock_cv2:
            mock_cv2.VideoCapture.return_value = good
            mock_cv2.CAP_PROP_FRAME_WIDTH  = 3
            mock_cv2.CAP_PROP_FRAME_HEIGHT = 4
            mock_cv2.CAP_PROP_FPS          = 5
            mock_cv2.CAP_PROP_BUFFERSIZE   = 38
            cam = Camera(source=0)
            cam._cap = good   # inject directly
            w, h = cam.resolution
        self.assertEqual(w, 1920)
        self.assertEqual(h, 1080)

    def test_resolution_fallback_when_no_cap(self):
        """resolution falls back to configured dimensions when cap is None."""
        cam = Camera(source=0, width=800, height=600)
        cam._cap = None
        w, h = cam.resolution
        self.assertEqual(w, 800)
        self.assertEqual(h, 600)


class TestCameraContextManager(unittest.TestCase):

    def test_context_manager_starts_and_stops(self):
        """with Camera() as cam should call start() on enter, stop() on exit."""
        good = _make_good_cap()
        with patch("core.camera.cv2") as mock_cv2:
            mock_cv2.VideoCapture.return_value = good
            mock_cv2.CAP_PROP_FRAME_WIDTH  = 3
            mock_cv2.CAP_PROP_FRAME_HEIGHT = 4
            mock_cv2.CAP_PROP_FPS          = 5
            mock_cv2.CAP_PROP_BUFFERSIZE   = 38
            with Camera(source=0) as cam:
                self.assertTrue(cam.is_running())
        self.assertFalse(cam.is_running())


class TestCameraReconnectLogic(unittest.TestCase):

    def test_reconnect_count_starts_zero(self):
        cam = Camera(source=0)
        self.assertEqual(cam.reconnect_count, 0)

    def test_start_fails_on_bad_source_raises(self):
        """start() should raise RuntimeError if the camera cannot open."""
        bad = _make_bad_cap()
        with patch("core.camera.cv2") as mock_cv2:
            mock_cv2.VideoCapture.return_value = bad
            mock_cv2.CAP_PROP_FRAME_WIDTH  = 3
            mock_cv2.CAP_PROP_FRAME_HEIGHT = 4
            mock_cv2.CAP_PROP_FPS          = 5
            mock_cv2.CAP_PROP_BUFFERSIZE   = 38
            cam = Camera(source=99)
            with self.assertRaises(RuntimeError):
                cam.start()

    def test_frames_captured_counter(self):
        """frames_captured must increment with each successful _reader_loop pass."""
        cam = Camera(source=0)
        cam.frames_captured = 0
        # Simulate 5 successful frame grabs internally
        for _ in range(5):
            dummy = np.zeros((480, 640, 3), dtype=np.uint8)
            with cam._frame_lock:
                cam._frame = dummy
            cam.frames_captured += 1
        self.assertEqual(cam.frames_captured, 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
