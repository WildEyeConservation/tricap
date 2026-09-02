import configparser
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

from flask import Flask
from support.local_network import web_client_allowed


ROOT = Path(__file__).resolve().parents[1]
VIEW_PATH = ROOT / "app" / "views" / "dashboard.py"
VIEW_SPEC = importlib.util.spec_from_file_location("skyseeker_dashboard_view", VIEW_PATH)
DASHBOARD_VIEW = importlib.util.module_from_spec(VIEW_SPEC)
VIEW_SPEC.loader.exec_module(DASHBOARD_VIEW)


class WebAccessTests(unittest.TestCase):
    def test_loopback_ap_wired_and_netbird_clients_are_allowed(self):
        for address in (
            "127.0.0.1",
            "::1",
            "192.168.50.42",
            "192.168.51.42",
            "100.64.0.1",
            "100.127.255.254",
        ):
            with self.subTest(address=address):
                self.assertTrue(web_client_allowed(address))

    def test_upstream_and_invalid_clients_are_rejected(self):
        for address in (
            None,
            "",
            "not-an-address",
            "10.0.0.20",
            "172.16.0.20",
            "192.168.1.20",
            "192.168.43.20",
            "203.0.113.20",
        ):
            with self.subTest(address=address):
                self.assertFalse(web_client_allowed(address))

    def test_wired_maintenance_profile_provides_laptop_addressing(self):
        profile = configparser.ConfigParser()
        profile.read(
            ROOT
            / "services"
            / "NetworkManager"
            / "system-connections"
            / "skyseeker-wired-access.nmconnection"
        )

        self.assertEqual(profile["connection"]["type"], "ethernet")
        self.assertEqual(profile["ipv4"]["method"], "shared")
        self.assertEqual(profile["ipv4"]["address1"], "192.168.51.1/24")
        self.assertEqual(profile["ipv4"]["never-default"], "true")

    def test_flask_runs_directly_on_http_port(self):
        launcher = (ROOT / "tricap.py").read_text()
        self.assertIn('host="0.0.0.0", port=80', launcher)
        self.assertFalse(
            (ROOT / "skyseeker-standalone" / "captive_portal.py").exists()
        )
        self.assertFalse(
            (ROOT / "services" / "systemd" / "skyseeker-portal.service").exists()
        )


class FlaskDashboardAssetTests(unittest.TestCase):
    def setUp(self):
        app = Flask(
            __name__,
            template_folder=str(ROOT / "app" / "templates"),
            static_folder=str(ROOT / "app" / "static"),
        )
        app.register_blueprint(DASHBOARD_VIEW.dashboard_bp)
        app.config["UI_SETTINGS"] = {"status_poll_ms": 1500, "heartbeat_ms": 7000}
        self.client = app.test_client()

    def test_flask_owns_operator_pages_and_health(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/setup").status_code, 200)
        self.assertEqual(self.client.get("/healthz").get_json(), {"ok": True})

    def test_flask_owns_uplink_endpoints(self):
        with patch.object(DASHBOARD_VIEW, "uplink_status", return_value={"available": True}):
            self.assertEqual(
                self.client.get("/api/uplink_status").get_json(),
                {"available": True},
            )
        with patch.object(DASHBOARD_VIEW, "uplink_connect", return_value=(True, "joined")) as connect:
            response = self.client.post(
                "/api/uplink_connect",
                json={"ssid": "field-hotspot", "psk": "secret"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json(), {"success": True, "msg": "joined"})
            connect.assert_called_once_with("field-hotspot", "secret")

    def test_templates_load_only_compiled_typescript(self):
        for page in ("home", "setup"):
            template = (ROOT / "app" / "templates" / "dashboard" / f"{page}.html").read_text()
            self.assertIn(f'/static/dist/{page}.js', template)
            self.assertNotIn("<style>", template)
            # One compiled module plus the [Ui] JSON data block, which is not executable.
            self.assertEqual(template.count("<script"), 2)
            self.assertEqual(template.count('script type="module"'), 1)
            self.assertEqual(template.count('script type="application/json" id="ui-config"'), 1)

    def test_pages_embed_the_configured_poll_rates(self):
        for path in ("/", "/setup"):
            html = self.client.get(path).get_data(as_text=True)
            self.assertIn(
                '<script type="application/json" id="ui-config">'
                '{"heartbeat_ms": 7000, "status_poll_ms": 1500}</script>',
                html,
            )

    def test_polling_remains_single_flight_and_capture_aware(self):
        home = (ROOT / "frontend" / "home.ts").read_text()
        setup = (ROOT / "frontend" / "setup.ts").read_text()
        common = (ROOT / "frontend" / "common.ts").read_text()

        self.assertIn("runPeriodic(connectionHeartbeat, uiConfig.heartbeat_ms)", common)
        self.assertIn("runPeriodic(pollStatus, uiConfig.status_poll_ms)", home)
        self.assertIn('singleFlight("home-status"', home)
        self.assertIn('singleFlight("home-storage"', home)
        self.assertIn('latest?.mode === "STARTED" ? undefined : pollStorage()', home)
        self.assertIn('singleFlight("setup-status"', setup)
        self.assertIn('singleFlight("setup-stats"', setup)
        self.assertIn('singleFlight("setup-image-format"', setup)
        self.assertIn("capturing ? uiConfig.sensors_poll_capturing_ms : uiConfig.sensors_poll_ms", setup)
        self.assertIn("capturing ? undefined : loadStats()", setup)


class AccessPointSignalTests(unittest.TestCase):
    def setUp(self):
        with DASHBOARD_VIEW._wifi_lock:
            DASHBOARD_VIEW._wifi_cache.update(
                ts=0.0, ap=None, stations={}, clients={}
            )

    def test_requesting_client_station_is_preferred(self):
        stations = {"aa:aa:aa:aa:aa:aa": -68, "bb:bb:bb:bb:bb:bb": -42}
        with (
            patch.object(DASHBOARD_VIEW, "_scan_ap_stations", return_value=("wlan1", stations)),
            patch.object(DASHBOARD_VIEW, "_ip_to_mac", return_value="aa:aa:aa:aa:aa:aa"),
        ):
            self.assertEqual(DASHBOARD_VIEW.ap_wifi_signal("192.168.50.20"), -68)

    def test_strongest_station_is_used_without_a_client_match(self):
        stations = {"aa:aa:aa:aa:aa:aa": -68, "bb:bb:bb:bb:bb:bb": -42}
        with patch.object(DASHBOARD_VIEW, "_scan_ap_stations", return_value=("wlan1", stations)):
            self.assertEqual(DASHBOARD_VIEW.ap_wifi_signal(), -42)

    def test_requesting_client_mac_is_cached_within_wifi_ttl(self):
        stations = {"aa:aa:aa:aa:aa:aa": -68}
        neighbor = "192.168.50.20 dev wlan1 lladdr aa:aa:aa:aa:aa:aa REACHABLE\n"
        with (
            patch.object(
                DASHBOARD_VIEW,
                "_scan_ap_stations",
                return_value=("wlan1", stations),
            ),
            patch.object(
                DASHBOARD_VIEW.subprocess,
                "check_output",
                return_value=neighbor,
            ) as check_output,
        ):
            self.assertEqual(DASHBOARD_VIEW.ap_wifi_signal("192.168.50.20"), -68)
            self.assertEqual(DASHBOARD_VIEW.ap_wifi_signal("192.168.50.20"), -68)

        check_output.assert_called_once_with(
            ["ip", "neigh", "show", "192.168.50.20"], text=True, timeout=3
        )


class StorageImageSampleTests(unittest.TestCase):
    def test_unmounted_internal_storage_is_unavailable(self):
        DASHBOARD_VIEW._storage_sample_cache = {"ts": 0.0, "payload": None}
        with patch.object(DASHBOARD_VIEW.os.path, "ismount", return_value=False):
            payload = DASHBOARD_VIEW.storage_image_sample()

        self.assertEqual(
            payload,
            {
                "available": False,
                "freeBytes": None,
                "averageImageBytes": None,
                "sampleCount": 0,
                "message": "Internal storage is not mounted.",
            },
        )


if __name__ == "__main__":
    unittest.main()
