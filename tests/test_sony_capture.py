"""Deterministic tests for the Sony SDK capture loop."""

import math
import tempfile
import threading
import unittest
from datetime import datetime
from unittest.mock import Mock, patch

from config import CAMERA_STATES
from sensors.sonySDK_cam import sonySDKcam


class FakeClock:

    def __init__(self, values):
        self._values = iter(values)
        self.current = None
        self._last = values[-1]

    def monotonic(self):
        try:
            self.current = next(self._values)
        except StopIteration:
            self.current = self._last
        return self.current


class SonyCaptureTests(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.sdk = Mock()
        self.sdk.setSaveInfo.return_value = True
        self.sdk.isConnected.return_value = True
        self.sdk.shutterDown.return_value = True
        self.sdk.shutterUp.return_value = True
        self.camera = sonySDKcam.__new__(sonySDKcam)
        self.camera._sonyCamera = self.sdk
        self.camera._cameraID = 1
        self.camera._capture_lock = threading.Lock()
        self.camera._count_lock = threading.Lock()
        self.camera._image_count = 0
        self.camera._num_images_copied = 0
        self.camera._num_images_failed = 0
        self.camera._downLoadedCount = 0
        self.camera._triggers = 0
        self.camera.last_error = None
        self.camera.state = CAMERA_STATES.INITIALISED

    def _capture_args(self, stop_capture, capture_done):
        return (
            self.temp_dir.name,
            2.0,
            10.0,
            datetime(2026, 9, 2, 12, 30, 0),
            "camera-one",
            stop_capture,
            threading.Lock(),
            0,
            capture_done,
            threading.Lock(),
        )

    def _run_capture(self, clock, stop_capture, capture_done, errors=None):
        errors = errors if errors is not None else []

        def target():
            try:
                self.camera.capture_and_copy(
                    *self._capture_args(stop_capture, capture_done)
                )
            except Exception as exc:
                errors.append(exc)

        with patch("sensors.sonySDK_cam.time.monotonic", clock.monotonic), \
                patch("sensors.sonySDK_cam.sleep"):
            thread = threading.Thread(target=target)
            thread.start()
            thread.join(timeout=1)
            if thread.is_alive():
                stop_capture.set()
                thread.join(timeout=1)
            self.assertFalse(thread.is_alive(), "capture thread did not exit")

        return errors

    def test_triggers_on_each_scheduled_slot_and_updates_counters(self):
        boundary = math.nextafter(10.0, math.inf)
        clock = FakeClock([
            10.0,
            boundary,
            boundary,
            12.0 + (boundary - 10.0),
            12.0 + (boundary - 10.0),
            14.0 + (boundary - 10.0),
            14.0 + (boundary - 10.0),
        ])
        stop_capture = threading.Event()
        capture_done = [threading.Event()]
        trigger_times = []

        def shutter_down(_camera_id):
            trigger_times.append(clock.current)
            return True

        def shutter_up(_camera_id):
            self.camera.imageDownloadCompleteCallback("image.jpg")
            if len(trigger_times) == 3:
                stop_capture.set()
            return True

        self.sdk.shutterDown.side_effect = shutter_down
        self.sdk.shutterUp.side_effect = shutter_up

        errors = self._run_capture(clock, stop_capture, capture_done)

        self.assertEqual(errors, [])
        self.assertEqual(
            trigger_times,
            [
                boundary,
                12.0 + (boundary - 10.0),
                14.0 + (boundary - 10.0),
            ],
        )
        self.assertTrue(capture_done[0].is_set())
        self.assertEqual(self.camera._triggers, 3)
        self.assertEqual(self.camera.get_cam_image_count(), 3)
        self.assertEqual(self.camera.get_cam_copy_count(), 3)

    def test_clock_jump_warns_once_and_resumes_at_next_slot(self):
        boundary = math.nextafter(10.0, math.inf)
        next_boundary = math.nextafter(18.0, math.inf)
        clock = FakeClock([
            boundary,
            boundary,
            17.2,
            17.2,
            17.2,
            17.2,
            next_boundary,
            next_boundary,
        ])
        stop_capture = threading.Event()
        capture_done = [threading.Event()]
        trigger_times = []

        def shutter_down(_camera_id):
            trigger_times.append(clock.current)
            return True

        def shutter_up(_camera_id):
            self.camera.imageDownloadCompleteCallback("image.jpg")
            if len(trigger_times) == 3:
                stop_capture.set()
            return True

        self.sdk.shutterDown.side_effect = shutter_down
        self.sdk.shutterUp.side_effect = shutter_up

        with self.assertLogs("sensors.sonySDK_cam", level="WARNING") as logs:
            errors = self._run_capture(clock, stop_capture, capture_done)

        skipped = [message for message in logs.output if "skipped" in message]
        self.assertEqual(errors, [])
        self.assertEqual(trigger_times, [boundary, 17.2, next_boundary])
        self.assertEqual(len(skipped), 1)
        self.assertIn("skipped 2 delayed capture slot(s)", skipped[0])
        self.assertTrue(capture_done[0].is_set())

    def test_error_callback_is_recorded_but_capture_continues(self):
        # SDK error callbacks can be transient (one failed transfer), so the
        # loop keeps shooting; the message stays visible on last_error.
        boundary = math.nextafter(10.0, math.inf)
        clock = FakeClock([boundary, boundary])
        stop_capture = threading.Event()
        capture_done = [threading.Event()]

        self.camera.cameraErrorCallback(b"camera overheated")

        def shutter_up(_camera_id):
            self.camera.imageDownloadCompleteCallback("image.jpg")
            stop_capture.set()
            return True

        self.sdk.shutterUp.side_effect = shutter_up
        errors = self._run_capture(clock, stop_capture, capture_done)

        self.assertEqual(errors, [])
        self.assertEqual(self.camera.last_error, "camera overheated")
        self.assertEqual(self.sdk.shutterDown.call_count, 1)
        self.assertEqual(self.camera.state, CAMERA_STATES.CAPTURING)
        self.assertTrue(capture_done[0].is_set())

    def test_trigger_exception_sets_error_state_and_done_event(self):
        boundary = math.nextafter(10.0, math.inf)
        clock = FakeClock([boundary])
        stop_capture = threading.Event()
        capture_done = [threading.Event()]
        self.sdk.shutterDown.side_effect = RuntimeError("SDK trigger failed")

        errors = self._run_capture(clock, stop_capture, capture_done)

        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], RuntimeError)
        self.assertEqual(
            (self.camera.state, capture_done[0].is_set()),
            (CAMERA_STATES.ERROR_CAPTURE, True),
        )


if __name__ == "__main__":
    unittest.main()
