# Repository audit and architecture

This document records the supported SkySeeker system after the repository
cleanup. A file is retained only when it is part of the deployed controller,
the reproducible build, focused verification, or current operating
documentation.

## Supported system

The deployed hardware boundary is:

- Sony cameras through the Sony Camera Remote SDK;
- GRF-500 laser altimeter;
- u-blox GPS on `/dev/gps`, including AssistNow data when an uplink and token
  are available;
- TP-Link RTL8192EU USB adapter dedicated to the access point;
- onboard Broadcom Wi-Fi for normal and rescue uplinks;
- direct Ethernet maintenance at `192.168.51.1`;
- GPIO capture switch and red/green status LEDs;
- internal capture storage and a removable USB backup volume.

There is no IMU, image geotagging, Canon/gPhoto camera path, simulated or dummy
sensor, Bluetooth path, SMS path, SD-card reader integration, protobuf layer,
or captive-portal process.

`UnavailableAltimeter` is not a simulator. It is a failure adapter that reports
the configured GRF-500 as unavailable and returns no measurements, allowing the
camera controller and web UI to start when the physical altimeter is missing.

## Runtime flow

```text
systemd tricap.service
└── tricap.py
    └── import app
        ├── load initial.cfg through TricapConfig
        ├── discover Sony SDK cameras
        │   └── TriCapCamsManager coordinates capture and storage
        ├── open /dev/gps
        │   ├── parse u-blox NMEA/UBX telemetry
        │   └── optionally download and upload AssistNow data
        ├── connect GRF-500
        │   └── use UnavailableAltimeter on connection failure
        ├── start GPIO switch, LED, and system monitors
        ├── start session and telemetry logging
        └── start Flask on port 80
            ├── render the home and setup templates
            ├── serve CSS, favicon, and compiled TypeScript output
            └── expose same-origin JSON, stream, log, and backup endpoints
```

Capture can be started from the browser or physical switch. The camera manager
starts GRF-500 measurement, triggers every discovered Sony camera at the
configured interval, and writes each camera's files beneath
`/mnt/ext_cam_storage/<date>/<session>/<camera>/`. GPS and altitude are logged
alongside the flight data, but they are never written into image metadata.
Backup operations verify and copy captures to `/mnt/ssd_cam_storage`.

The browser and Flask are one application boundary:

```text
browser
├── GET / or /setup ───────────────> Flask templates
├── GET /static/... ───────────────> Flask static files
└── same-origin /api/* requests ───> Flask blueprints
    ├── capture, preview, status and settings
    ├── storage verification, backup and log downloads
    ├── onboard-Wi-Fi uplink selection
    └── NetBird configuration and status
```

`frontend/*.ts` is the only browser source. `tsc` type-checks it in strict mode
and emits `app/static/dist/*.js`, because browsers execute JavaScript. Node is a
build tool only; it is not a deployed server. Flask directly serves the HTML,
generated JavaScript, CSS, API, and health endpoint. There is no proxy, WSGI
wrapper, separate frontend server, redirector, captive-portal detector, or
second diagnostics web server.

Flask accepts requests only from loopback, the access-point subnet, the wired
maintenance subnet, and the NetBird address range. The TP-Link adapter remains
dedicated to hostapd. The onboard radio keeps an existing uplink; only when
disconnected does the rescue timer scan for and join the pre-provisioned
`skyseeker-rescue` profile. NetBird runs independently and reconnects when that
uplink becomes usable.

## Used repository tree

The following is the complete tracked tree, grouped by purpose.

```text
.
├── tricap.py                         deployed Python entry point
├── app/
│   ├── __init__.py                   Flask app and hardware composition root
│   ├── views/
│   │   ├── __init__.py               Python package marker
│   │   ├── dashboard.py              pages, uplink, flight log, storage sample
│   │   └── api.py                    capture, preview, backup and NetBird API
│   ├── templates/dashboard/
│   │   ├── home.html                 flight dashboard shell
│   │   └── setup.html                device setup and maintenance shell
│   └── static/
│       ├── css/dashboard.css         operator UI styling
│       ├── img/favicon.ico           browser icon
│       └── dist/
│           ├── common.js             generated shared browser utilities
│           ├── home.js               generated flight-dashboard behavior
│           └── setup.js              generated setup behavior
├── frontend/
│   ├── common.ts                     typed fetch, clock and connectivity code
│   ├── home.ts                       typed flight-dashboard client
│   └── setup.ts                      typed setup and maintenance client
├── sensors/
│   ├── __init__.py                   Python package marker
│   ├── base_setting.py               shared validated hardware setting model
│   ├── cam_manager.py                Sony discovery, capture and storage owner
│   ├── sony_discovery.py             bounded Sony SDK discovery retries
│   ├── sonySDK_cam.py                Sony SDK camera adapter
│   ├── grf500_altimeter.py           GRF-500 serial protocol and measurement
│   ├── unavailable_altimeter.py      non-fabricating GRF-500 failure adapter
│   └── toggle_switch.py              GPIO switch, camera monitors and LEDs
├── serial_comms/
│   ├── __init__.py                   Python package marker
│   ├── SerialInterface.py            u-blox connection and reader threads
│   ├── SerialProcess.py              NMEA/UBX parsing and GPS CSV output
│   └── ubloxAgps.py                  optional u-blox AssistNow exchange
├── support/
│   ├── __init__.py                   Python package marker
│   ├── basic.py                      observer and periodic-monitor primitives
│   ├── configure.py                  supported initial.cfg reader/writer
│   ├── component_health.py           camera/GPS/altimeter health summary
│   ├── session_logger.py             per-flight logs and config snapshot
│   ├── system_monitor.py             CPU, RAM, disk and I/O logging
│   ├── phone_time.py                 validated browser-to-device clock sync
│   ├── local_network.py              Flask source-network allow-list
│   ├── git_info.py                   deployed revision reporting
│   └── backup.py                     copy, verification and safe-delete engine
├── services/
│   ├── README.md                     install, update and retirement procedure
│   ├── systemd/
│   │   ├── tricap.service            Flask/capture process supervision
│   │   ├── skyseeker-standalone-net.service  AP interface address
│   │   ├── skyseeker-ap-autodetect.service   TP-Link interface discovery
│   │   ├── skyseeker-firstboot.service       unique host identity generation
│   │   ├── skyseeker-health.service          one health/recovery execution
│   │   ├── skyseeker-health.timer            periodic bounded AP recovery
│   │   ├── skyseeker-recovery-scan.service   one rescue-uplink scan
│   │   └── skyseeker-recovery-scan.timer     periodic rescue scan
│   ├── NetworkManager/system-connections/
│   │   └── skyseeker-wired-access.nmconnection  direct Ethernet DHCP profile
│   ├── usr-local/sbin/
│   │   ├── skyseeker-ap-autodetect.sh        detect and pin RTL8192EU AP radio
│   │   ├── skyseeker-firstboot.sh            regenerate cloned identities
│   │   ├── skyseeker-health                  diagnostics and service recovery
│   │   └── skyseeker-recovery-scan           non-disruptive rescue joiner
│   ├── journald.conf.d/skyseeker-journald.conf  bounded persistent journal
│   ├── modprobe.d/skyseeker-8192eu.conf       disable AP driver power saving
│   └── udev-rules.d/99-skyseeker-ap-dongle.rules  disable USB autosuspend
├── tests/
│   ├── __init__.py                   test package marker
│   ├── test_backup.py                backup integrity and deletion safety
│   ├── test_component_health.py      hardware failure reporting
│   ├── test_configure.py             supported/retired config behavior
│   ├── test_dashboard.py             Flask ownership, access and UI assets
│   ├── test_grf500_altimeter.py      GRF-500 frames and settings
│   ├── test_gpio_controls.py         physical switch input and debounce
│   ├── test_network_health.py        bounded AP diagnostics and recovery
│   ├── test_phone_time.py            safe device clock updates
│   ├── test_recovery_scan.py         rescue scan and NetBird separation
│   ├── test_sony_camera_manager.py   discovered-camera construction
│   ├── test_sony_discovery.py        bounded SDK discovery
│   ├── test_sony_image_format.py     Sony connection and transfer settings
│   └── test_ublox_gps.py             GPS satellite and quality parsing
├── config.py                         runtime constants and state enums
├── local_paths.py                    deployed log, session and config paths
├── default.cfg                       only Sony, GRF-500 and capture settings
├── pyproject.toml                    locked Python dependency declaration
├── uv.lock                           exact Python dependency graph
├── package.json                      TypeScript build commands and dependency
├── package-lock.json                 exact frontend build dependency graph
├── tsconfig.json                     strict TypeScript compiler contract
├── README.md                         project entry documentation
├── docs/
│   ├── repository-audit.md           this architecture and cleanup ledger
│   └── stability-recovery-plan.md    current network recovery runbook
├── .gitattributes                    Linux line endings for deployed files
└── .gitignore                        local build, cache, secret and config data
```

The retained tests are not deployed to the device's service process, but they
protect the hardware and data-loss boundaries most likely to regress. The two
lockfiles and generated browser files are intentional: lockfiles reproduce the
build, while the generated JavaScript is the artifact Flask must serve.

## Abstractions retained deliberately

- `TriCapCamsManager` is the single coordinator for multiple Sony cameras,
  synchronized capture, storage mounts and backup hand-off. Removing it would
  spread concurrency and storage state through Flask routes.
- `SerialInterface` and `SerialProcess` separate serial lifetime from u-blox
  message interpretation. `ubloxAgps` remains separate because AssistNow is an
  HTTPS/UBX exchange, not normal streaming telemetry.
- `Subject`, `Observer` and `PeriodicMonitor` support the GRF-500 logger, GPIO
  switch and status LEDs. They are small shared primitives, not sensor plugins.
- `UnavailableAltimeter` preserves one GRF-500-shaped interface on a hardware
  fault without inventing values or selecting another sensor.
- `backup.py` is large, but its copy, verify and delete logic is one safety
  boundary. Hiding those operations behind additional service layers would not
  make the data-loss rules clearer.

No generic sensor registry, factory, simulator selection, protocol generator,
frontend framework, state store, proxy, or service-to-service HTTP layer is
retained.

## Redundant-file ledger

All files in the following groups were removed from the tracked repository.
Directory globs mean every previously tracked file beneath that directory.

| Removed group | Redundant files | Reason |
|---|---|---|
| Scratch scripts | `alk/**` | One-off GPS, IMU, GPIO, gPhoto, copy and radio experiments |
| Offline analysis | `analysis/**`, `split_rate_files.py` | Historical plotting and log-splitting tools, not flight runtime |
| Bluetooth | `bluez/**` | Retired BlueZ agent and utility layer |
| Canon/gPhoto fixtures | `camModels/**`, `sensors/abstract_cam.py`, `sensors/canon_6D.py`, `sensors/canon_R.py`, `sensors/gphoto_cam.py`, `sensors/gpio_cam.py` | Unsupported camera families and captured fixtures |
| Dummy/retired sensors | `sensors/alti_simulator.py`, `sensors/dummy_alti.py`, `sensors/dummy_cam.py`, `sensors/trusense_altimeter.py`, `sensors/altitude_switch.py`, `sensors/camera_logger.py`, `sensors/cam_manager.py.save.1` | Simulators, unsupported hardware and backup copies |
| IMU | `serial_comms/berryIMU.py`, `serial_comms/IMU.py`, `serial_comms/LIS3MDL.py`, `serial_comms/LSM6DSL.py`, `serial_comms/LSM9DS0.py`, `serial_comms/LSM9DS1.py` | IMU is no longer fitted or consumed |
| Protobuf | `tricap.proto`, `protobuf/**`, `serial_comms/out/**` | Generated protocol layer had no remaining producer or consumer |
| Image geotagging | `support/gps_geotag.py` | Geotagging was too slow and is no longer performed |
| SD-card reader | `SD_card_reader.py` | Unsupported external reader integration |
| SMS/phone/Bluetooth-era support | `support/sms_sender.py`, `support/phone_gps.py`, `support/talkbox.py`, `support/connection_monitor.py` | Retired communication paths |
| Old image/log models | `support/camera_data.py`, `support/camera_image.py`, `support/log_list.py` | Used only by the retired Flask pages |
| Old Flask UI | `app/forms.py`, `app/views/camera.py`, `app/views/home.py`, `app/views/settings.py`, `app/views/showlog.py`, `app/templates/base.html`, `app/templates/camera/**`, `app/templates/home/**`, `app/templates/settings/**`, `app/templates/showlog/**`, `app/templates/js/**` | Replaced by the two direct Flask operator pages |
| Old browser stack | `app/static/js/**`, old Bootstrap/Bootswatch/Font Awesome/Lato assets under `app/static/css/**` and `app/static/fonts/**`, `app/static/img/default.jpg`, `app/static/img/placeholder.png`, `app/static/img/Power-Shutdown.png` | jQuery and handwritten JavaScript UI replaced by strict TypeScript and one stylesheet |
| Captive portal | `skyseeker-standalone/captive_portal.py`, `services/systemd/skyseeker-portal.service` | Flask now serves the UI directly over the AP |
| Duplicate diagnostics/recovery | `services/usr-local/bin/skyseeker-diag.py`, `services/usr-local/sbin/skyseeker-ap-monitor`, `services/usr-local/sbin/skyseeker-ap-watchdog`, their systemd units/timers, `udp_ip.sh`, `udp-ip.service` | Consolidated into the dashboard, NetBird and `skyseeker-health` |
| Old launch/deploy files | `tricap.service`, `tricap.ini`, `wsgi.py`, `tricap_launcher.sh`, `tricap_launch_tester.py`, `tricap_loop.py`, `main_serial.py`, `python_setup.sh`, `setup.py`, `wifi_setup.sh`, `get_time_from_camera.sh`, `local_paths_example.py` | Duplicate, obsolete or replaced entry/deployment paths |
| Root artifacts | `.coveragerc`, `defaultend.jpg` | Unused coverage and image residue |
| Root test harnesses | `test_app.py`, `test_behaviour.py`, `test_live_server.py`, `test_sensors.py`, `test_unit.py` | Duplicate and hardware-stale test entry points |
| Obsolete tests | `tests/test_alti_simulator.py`, `tests/test_altitude_switch.py`, `tests/test_ap_monitor.py`, `tests/test_ap_watchdog.py`, `tests/test_basic.py`, `tests/test_camera_logger.py`, `tests/test_canon6d_cam.py`, `tests/test_captive_portal.py`, `tests/test_connection_monitor.py`, `tests/test_dummy_alti.py`, `tests/test_dummy_cam.py`, `tests/test_log_list.py`, `tests/test_page_camera_live_server.py`, `tests/test_page_home.py`, `tests/test_page_home_live_server.py`, `tests/test_session_logger.py`, `tests/test_settings.py`, `tests/test_sms_sender.py`, `tests/test_system_monitor.py`, `tests/test_talkbox.py`, `tests/test_trusense_altimeter.py`, `tests/tricap_flask_live_server_test_case.py`, `tests/tricap_flask_test_case.py`, `tests/tricap_tempfile_test_case.py` | Covered retired components, duplicate layers or brittle live-server scaffolding |

The cleanup also removed dead Web and SMS sections from `default.cfg`, prunes
those sections when an older `initial.cfg` is next saved, removed unused runtime
constants/imports, and deleted a captured AssistNow binary payload that had
been committed as a comment.

Ignored local directories such as `.venv/`, `node_modules/`, `__pycache__/`,
coverage output and logs are development products, not tracked repository
content. They may be deleted locally and are recreated by their respective
tools. An installed device can also remove the retired external services and
`/home/radxa/skyseeker-standalone/` using the migration commands in
`services/README.md`.

## Audit result

No tracked file is currently known to be redundant. The remaining Python
modules are reachable from the deployed entry point or provide a focused
hardware/data-safety test. The remaining TypeScript, generated JavaScript,
configuration, service, lock and documentation files each have a defined build
or deployment consumer.

The only automatic recovery action is a bounded restart of failed hostapd or
dnsmasq after three failed health checks and a ten-minute cooldown. A hidden
camera-error reboot path found during this audit was removed. Reboot remains an
explicit operator action in the setup UI; no monitor, capture callback or timer
can invoke it.
