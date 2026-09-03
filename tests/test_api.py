"""Tests for the API safety interlocks: refuse at the wrong moment, act otherwise."""

import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from flask import Flask

from config import CAM_MANAGER_STATES, MOUNT_POINT, MOUNT_POINT_SSD

ROOT = Path(__file__).resolve().parents[1]

# app/views/api.py imports its collaborators from the app package, whose
# import constructs the camera manager and opens serial ports. A stub package
# with the same attributes lets the blueprint import without any hardware.
if "app" not in sys.modules:
    stub_app = types.ModuleType("app")
    stub_app.__path__ = [str(ROOT / "app")]
    for name in ("altimeter", "clock", "gps_ser", "tricap_manager"):
        setattr(stub_app, name, Mock())
    sys.modules["app"] = stub_app

from app.views import api as API  # noqa: E402

BUSY_STATES = (CAM_MANAGER_STATES.STARTED, CAM_MANAGER_STATES.COPYING)
IDLE = {"running": False}
RUNNING = {"running": True}


class ApiInterlockTests(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.register_blueprint(API.api_bp)
        self.client = app.test_client()

        self.manager = Mock()
        self.manager.state = CAM_MANAGER_STATES.STOPPED
        self.manager.get_cameras_as_list.return_value = [Mock()]
        self.manager.start_capturing.return_value = True
        self.manager.mount_ssd.return_value = True
        self.backup = Mock()
        self.backup.status.return_value = dict(IDLE)
        self.backup.verify_delete_status.return_value = dict(IDLE)
        self.backup.start.return_value = {"success": True}
        self.backup.start_verify_and_delete.return_value = {"success": True}
        self.clock = Mock()
        self.schedule = Mock()

        for target, value in (
            ("tricap_manager", self.manager),
            ("backupManager", self.backup),
            ("clock", self.clock),
            ("_schedule_system_action", self.schedule),
        ):
            patcher = patch.object(API, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

        self.force_status = dict(API._force_delete_status)
        self.addCleanup(API._force_delete_status.update, self.force_status)

    def _busy(self, state):
        self.manager.state = state

    # -- capture -----------------------------------------------------------

    def test_start_capture_refuses_when_already_started(self):
        self._busy(CAM_MANAGER_STATES.STARTED)
        response = self.client.post("/api/start_capture")
        self.assertEqual(response.status_code, 400)
        self.manager.start_capturing.assert_not_called()

    def test_start_capture_refuses_without_cameras(self):
        self.manager.get_cameras_as_list.return_value = []
        response = self.client.post("/api/start_capture")
        self.assertEqual(response.status_code, 409)
        self.manager.start_capturing.assert_not_called()

    def test_start_capture_reports_storage_refusal(self):
        self.manager.start_capturing.return_value = False
        response = self.client.post("/api/start_capture")
        self.assertEqual(response.status_code, 409)
        self.assertIn("storage", response.get_json()["msg"].lower())

    def test_start_capture_succeeds_when_manager_starts(self):
        response = self.client.post("/api/start_capture")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["success"])
        self.manager.start_capturing.assert_called_once_with()

    def test_stop_capture_refuses_when_stopped_and_stops_otherwise(self):
        response = self.client.post("/api/stop_capture")
        self.assertEqual(response.status_code, 400)
        self.manager.stop_capturing.assert_not_called()

        self._busy(CAM_MANAGER_STATES.STARTED)
        response = self.client.post("/api/stop_capture")
        self.assertEqual(response.status_code, 200)
        self.manager.stop_capturing.assert_called_once_with()

    # -- restart / reboot --------------------------------------------------

    def test_restart_and_reboot_refuse_during_capture_and_copy(self):
        for state in BUSY_STATES:
            for path in ("/api/restart", "/api/reboot"):
                with self.subTest(state=state.name, path=path):
                    self._busy(state)
                    response = self.client.post(path)
                    self.assertEqual(response.status_code, 409)
        self.schedule.assert_not_called()

    def test_restart_and_reboot_refuse_while_storage_job_runs(self):
        self.backup.status.return_value = dict(RUNNING)
        self.assertEqual(self.client.post("/api/restart").status_code, 409)
        self.backup.status.return_value = dict(IDLE)

        self.backup.verify_delete_status.return_value = dict(RUNNING)
        self.assertEqual(self.client.post("/api/reboot").status_code, 409)
        self.backup.verify_delete_status.return_value = dict(IDLE)

        API._force_delete_status["running"] = True
        self.assertEqual(self.client.post("/api/restart").status_code, 409)
        self.schedule.assert_not_called()

    def test_restart_and_reboot_schedule_the_system_action_when_idle(self):
        response = self.client.post("/api/restart")
        self.assertEqual(response.status_code, 200)
        self.schedule.assert_called_once_with(["systemctl", "--no-block", "restart", "tricap.service"])

        self.schedule.reset_mock()
        response = self.client.post("/api/reboot")
        self.assertEqual(response.status_code, 200)
        self.schedule.assert_called_once_with(["systemctl", "reboot"])

    # -- clock -------------------------------------------------------------

    def test_sync_phone_time_refuses_during_capture(self):
        self._busy(CAM_MANAGER_STATES.COPYING)
        response = self.client.post(
            "/api/sync_phone_time", json={"epochMs": 1_700_000_000_000, "timezoneOffsetMinutes": -120}
        )
        self.assertEqual(response.status_code, 409)
        self.clock.sync_from_phone.assert_not_called()

    def test_sync_phone_time_rejects_bad_payload(self):
        response = self.client.post("/api/sync_phone_time", json={"epochMs": "soon"})
        self.assertEqual(response.status_code, 400)
        self.clock.sync_from_phone.assert_not_called()

    def test_sync_phone_time_applies_valid_payload(self):
        self.clock.sync_from_phone.return_value = {
            "source": "phone",
            "timeApplied": True,
            "timezone": "Etc/GMT-2",
            "adjustmentMs": 5,
            "rtcSynced": True,
            "camerasSynced": 1,
            "cameraErrors": [],
        }
        with patch.object(API, "validate_phone_time", return_value=(1_700_000_000_000, -120)):
            response = self.client.post(
                "/api/sync_phone_time", json={"epochMs": 1_700_000_000_000, "timezoneOffsetMinutes": -120}
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["success"])
        self.clock.sync_from_phone.assert_called_once_with(1_700_000_000_000, -120)

    # -- backup ------------------------------------------------------------

    def test_backup_endpoints_refuse_during_capture_and_copy(self):
        for state in BUSY_STATES:
            for path in ("/api/backup_start", "/api/backup_move", "/api/backup_stop", "/api/verify_and_delete"):
                with self.subTest(state=state.name, path=path):
                    self._busy(state)
                    self.assertEqual(self.client.post(path).status_code, 400)
        self.backup.start.assert_not_called()
        self.backup.start_verify_and_delete.assert_not_called()
        self.manager.mount_ssd.assert_not_called()

    def test_backup_start_and_move_call_the_manager_with_the_rig_paths(self):
        response = self.client.post("/api/backup_start")
        self.assertEqual(response.status_code, 202)
        self.backup.start.assert_called_once_with(MOUNT_POINT, MOUNT_POINT_SSD)

        self.backup.start.reset_mock()
        response = self.client.post("/api/backup_move")
        self.assertEqual(response.status_code, 202)
        self.backup.start.assert_called_once_with(MOUNT_POINT, MOUNT_POINT_SSD, remove_source=True)

    def test_backup_refusal_by_manager_unmounts_the_ssd_again(self):
        self.backup.start.return_value = {"success": False, "msg": "Backup is running"}
        response = self.client.post("/api/backup_start")
        self.assertEqual(response.status_code, 400)
        self.manager.unmount_disk.assert_called_once_with()

    def test_backup_start_reports_ssd_mount_failure(self):
        self.manager.mount_ssd.return_value = False
        response = self.client.post("/api/backup_start")
        self.assertEqual(response.status_code, 400)
        self.backup.start.assert_not_called()

    def test_verify_and_delete_does_not_restart_a_running_verification(self):
        self.backup.verify_delete_status.return_value = dict(RUNNING)
        response = self.client.post("/api/verify_and_delete")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()["started"])
        self.backup.start_verify_and_delete.assert_not_called()

    def test_verify_and_delete_starts_and_unmounts_on_refusal(self):
        response = self.client.post("/api/verify_and_delete")
        self.assertEqual(response.status_code, 202)
        self.backup.start_verify_and_delete.assert_called_once_with(MOUNT_POINT, MOUNT_POINT_SSD)

        self.backup.start_verify_and_delete.return_value = {"success": False, "code": "destination_not_mounted"}
        response = self.client.post("/api/verify_and_delete")
        self.assertEqual(response.status_code, 409)
        self.manager.unmount_disk.assert_called_once_with()

    # -- force delete ------------------------------------------------------

    def _force_delete(self, confirmed=True):
        payload = {"confirmation": API._FORCE_DELETE_CONFIRMATION} if confirmed else {}
        return self.client.post("/api/force_delete", json=payload)

    def test_force_delete_refuses_during_capture_or_other_storage_jobs(self):
        with patch.object(API.threading, "Thread") as thread:
            self._busy(CAM_MANAGER_STATES.STARTED)
            self.assertEqual(self._force_delete().status_code, 400)
            self._busy(CAM_MANAGER_STATES.STOPPED)

            self.backup.status.return_value = dict(RUNNING)
            self.assertEqual(self._force_delete().status_code, 409)
            self.backup.status.return_value = dict(IDLE)

            self.backup.verify_delete_status.return_value = dict(RUNNING)
            self.assertEqual(self._force_delete().status_code, 409)
            self.backup.verify_delete_status.return_value = dict(IDLE)

            API._force_delete_status["running"] = True
            with patch.object(API.os.path, "ismount", return_value=True):
                self.assertEqual(self._force_delete().status_code, 409)
        thread.assert_not_called()

    def test_force_delete_requires_confirmation_and_a_mounted_disk(self):
        with patch.object(API.threading, "Thread") as thread:
            response = self._force_delete(confirmed=False)
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.get_json()["code"], "confirmation_required")

            with patch.object(API.os.path, "ismount", return_value=False):
                response = self._force_delete()
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.get_json()["code"], "internal_not_mounted")
        thread.assert_not_called()

    def test_force_delete_targets_only_the_internal_mount_point(self):
        with patch.object(API.threading, "Thread") as thread, patch.object(API.os.path, "ismount", return_value=True):
            response = self._force_delete()
        self.assertEqual(response.status_code, 202)
        thread.assert_called_once()
        self.assertEqual(thread.call_args.kwargs["args"], (Path(MOUNT_POINT).resolve(),))
        self.assertTrue(API._force_delete_status["running"])

    # -- read-only endpoints ----------------------------------------------

    def test_statistics_refuses_during_capture(self):
        self._busy(CAM_MANAGER_STATES.STARTED)
        self.assertEqual(self.client.get("/api/statistics").status_code, 400)

    def test_statistics_reports_internal_disk_only_when_mounted(self):
        self.manager.get_image_capture_interval.return_value = 2.5
        self.manager.ssd_usage.return_value = {}
        with patch.object(API.os.path, "ismount", return_value=False):
            unmounted = self.client.get("/api/statistics").get_json()
        self.assertEqual(unmounted["internalStorage"], {})

        gib = 1073741824
        with (
            patch.object(API.os.path, "ismount", return_value=True),
            patch.object(API.shutil, "disk_usage", return_value=(4 * gib, 1 * gib, 3 * gib)),
        ):
            mounted = self.client.get("/api/statistics").get_json()
        self.assertEqual(mounted["internalStorage"]["capacityGB"], 4.0)
        self.assertEqual(mounted["internalStorage"]["freeGB"], 3.0)

    def test_download_logs_refuses_during_capture_and_404s_when_missing(self):
        self._busy(CAM_MANAGER_STATES.COPYING)
        self.assertEqual(self.client.get("/api/download_logs").status_code, 400)

        self._busy(CAM_MANAGER_STATES.STOPPED)
        with tempfile.TemporaryDirectory() as empty_dir, patch.object(API, "SERVER_LOG_DIR", empty_dir):
            self.assertEqual(self.client.get("/api/download_logs").status_code, 404)


if __name__ == "__main__":
    unittest.main()
