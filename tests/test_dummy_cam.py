"""Test the dummy cam."""

import threading
from time import sleep

from unittest import TestCase

from sensors.dummy_cam import DummyCam
from support.configure import TricapConfig


class TestDummyCam(TestCase):
    """Test dummy cam."""

    def create_cam(self, settings=None):
        """Create an cam."""
        if settings is None:
            settings = self.base_settings

        autodetect_results = DummyCam.autodetect()

        self.cam = DummyCam(autodetect_results[0][1], settings)

    @property
    def base_settings(self):
        """The settings from the config file."""
        init_config = TricapConfig()
        return init_config.get_section_dict(TricapConfig.CAMERA_SECTION_HEADER)

    def test_capture_cycle(self):
        """Test a capture cycle can run without issue."""
        self.create_cam()

        kill_pill = threading.Event()

        self.cam.generation_period = 0.1

        thread = threading.Thread(target=self.cam.capture, daemon=True,
                                  kwargs={"continuous": True,
                                          "stop_event": kill_pill})

        self.assertEqual(self.cam.is_cam_image_fresh(), False)

        thread.start()
        self.assertEqual(self.cam.get_state_as_string(), 'CAPTURING')

        # check that a new image is "released" and that the camera keeps track of access
        sleep(self.cam.generation_period*2)
        self.assertEqual(self.cam.is_cam_image_fresh(), True)
        self.assertNotEqual(self.cam.data, None)
        self.assertEqual(self.cam.is_cam_image_fresh(), False)

        # check that a new image is refereshed
        sleep(self.cam.generation_period*2)
        self.assertEqual(self.cam.is_cam_image_fresh(), True)

        # coverage maxing
        self.assertEqual(self.cam.serial_num, 0)

        kill_pill.set()
        thread.join()
