import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

from flask import Flask


ROOT = Path(__file__).resolve().parents[1]
FORWARDER_PATH = ROOT / "skyseeker-standalone" / "captive_portal.py"
SPEC = importlib.util.spec_from_file_location("skyseeker_forwarder", FORWARDER_PATH)
FORWARDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FORWARDER)
VIEW_PATH = ROOT / "app" / "views" / "portal.py"
VIEW_SPEC = importlib.util.spec_from_file_location("skyseeker_portal_view", VIEW_PATH)
PORTAL_VIEW = importlib.util.module_from_spec(VIEW_SPEC)
VIEW_SPEC.loader.exec_module(PORTAL_VIEW)


class PortForwarderTests(unittest.TestCase):
    def test_rejoin_queue_capacity_is_preserved(self):
        self.assertEqual(FORWARDER.PortalServer.request_queue_size, 50)
        self.assertTrue(FORWARDER.PortalServer.daemon_threads)
        self.assertFalse(FORWARDER.PortalServer.block_on_close)

    def test_every_http_method_forwards_to_flask(self):
        self.assertIs(FORWARDER.Handler.do_GET, FORWARDER.Handler._proxy)
        self.assertIs(FORWARDER.Handler.do_HEAD, FORWARDER.Handler._proxy)
        self.assertIs(FORWARDER.Handler.do_POST, FORWARDER.Handler._proxy)


class FlaskPortalAssetTests(unittest.TestCase):
    def setUp(self):
        app = Flask(
            __name__,
            template_folder=str(ROOT / "app" / "templates"),
            static_folder=str(ROOT / "app" / "static"),
        )
        app.register_blueprint(PORTAL_VIEW.portal_bp)
        self.client = app.test_client()

    def test_flask_owns_operator_pages_and_health(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/setup").status_code, 200)
        self.assertEqual(self.client.get("/healthz").get_json(), {"ok": True})

    def test_flask_owns_uplink_endpoints(self):
        with patch.object(PORTAL_VIEW, "uplink_status", return_value={"available": True}):
            self.assertEqual(
                self.client.get("/portal/uplink_status").get_json(),
                {"available": True},
            )
        with patch.object(PORTAL_VIEW, "uplink_connect", return_value=(True, "joined")) as connect:
            response = self.client.post(
                "/portal/uplink_connect",
                json={"ssid": "field-hotspot", "psk": "secret"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json(), {"success": True, "msg": "joined"})
            connect.assert_called_once_with("field-hotspot", "secret")

    def test_templates_load_only_compiled_typescript(self):
        for page in ("home", "setup"):
            template = (ROOT / "app" / "templates" / "portal" / f"{page}.html").read_text()
            self.assertIn(f'/static/dist/{page}.js', template)
            self.assertNotIn("<style>", template)
            self.assertEqual(template.count("<script"), 1)
            self.assertIn('script type="module"', template)

    def test_polling_remains_single_flight_and_capture_aware(self):
        home = (ROOT / "frontend" / "home.ts").read_text()
        setup = (ROOT / "frontend" / "setup.ts").read_text()
        common = (ROOT / "frontend" / "common.ts").read_text()

        self.assertIn("runPeriodic(connectionHeartbeat, 5000)", common)
        self.assertIn("runPeriodic(pollStatus, 1000)", home)
        self.assertIn('singleFlight("home-status"', home)
        self.assertIn('singleFlight("home-storage"', home)
        self.assertIn('latest?.mode === "STARTED" ? undefined : pollStorage()', home)
        self.assertIn('singleFlight("setup-status"', setup)
        self.assertIn('singleFlight("setup-stats"', setup)
        self.assertIn('singleFlight("setup-image-format"', setup)
        self.assertIn("capturing ? 5000 : 2000", setup)
        self.assertIn("capturing ? undefined : loadStats()", setup)


class AccessPointSignalTests(unittest.TestCase):
    def test_requesting_client_station_is_preferred(self):
        stations = {"aa:aa:aa:aa:aa:aa": -68, "bb:bb:bb:bb:bb:bb": -42}
        with (
            patch.object(PORTAL_VIEW, "_scan_ap_stations", return_value=("wlan1", stations)),
            patch.object(PORTAL_VIEW, "_ip_to_mac", return_value="aa:aa:aa:aa:aa:aa"),
        ):
            self.assertEqual(PORTAL_VIEW.ap_wifi_signal("192.168.4.20"), -68)

    def test_strongest_station_is_used_without_a_client_match(self):
        stations = {"aa:aa:aa:aa:aa:aa": -68, "bb:bb:bb:bb:bb:bb": -42}
        with patch.object(PORTAL_VIEW, "_scan_ap_stations", return_value=("wlan1", stations)):
            self.assertEqual(PORTAL_VIEW.ap_wifi_signal(), -42)


if __name__ == "__main__":
    unittest.main()
