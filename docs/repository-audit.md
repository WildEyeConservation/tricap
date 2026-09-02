# Repository audit and architecture

This document records the supported SkySeeker system after the repository
cleanup. A file is retained only when it is part of the deployed controller,
the reproducible build, focused verification, or current operating
documentation.

## Supported system

The deployed hardware boundary is:

- Sony cameras through the Sony Camera Remote SDK;
- GRF-500 laser altimeter;
- u-blox GPS on `/dev/gps`;
- TP-Link RTL8192EU USB adapter dedicated to the access point;
- onboard Broadcom Wi-Fi for normal and rescue uplinks;
- direct Ethernet maintenance at `192.168.51.1`;
- internal capture storage and a removable USB backup volume.

There is no IMU, image geotagging, Canon/gPhoto camera path, simulated or dummy
sensor, Bluetooth path, SMS path, SD-card reader integration, protobuf layer,
captive-portal process, GPIO switch/LED path, or AssistNow (A-GPS) exchange.

`UnavailableAltimeter` is not a simulator. It is a failure adapter that reports
the configured GRF-500 as unavailable and returns no measurements, allowing the
camera controller and web UI to start when the physical altimeter is missing.

## Runtime flow

```text
systemd tricap.service
└── tricap.py
    └── import app
        ├── load default.cfg, then initial.cfg overrides, through TricapConfig
        ├── discover Sony SDK cameras
        │   └── TriCapCamsManager coordinates capture and storage
        ├── open /dev/gps
        │   └── parse u-blox NMEA telemetry
        ├── connect GRF-500
        │   └── use UnavailableAltimeter on connection failure
        ├── start telemetry logging
        └── start Flask on port 80
            ├── render the home and setup templates
            ├── serve CSS, favicon, and compiled TypeScript output
            └── expose same-origin JSON, stored-image sample, log, and backup endpoints
```

`tricap.py` handles `SIGTERM` by stopping capture, stopping the laser altimeter,
unmounting the external SSD, and then exiting.

Capture is started and stopped from the browser. The camera manager starts
GRF-500 measurement and triggers every discovered Sony camera at the configured
interval. The Sony SDK writes files directly to
`/mnt/ext_cam_storage/<date>/<session>/<serial>/`; there is no application save
thread, preview-image pipeline, tmpfs mount, or `memoryFs` path. GPS and altitude
are logged alongside the flight data but are never written into image metadata.
Backup operations verify and copy captures to `/mnt/ssd_cam_storage`.

The browser and Flask are one application boundary:

```text
browser
├── GET / or /setup ───────────────> Flask templates
├── GET /static/... ───────────────> Flask static files
└── same-origin /api/* requests ───> Flask blueprints
    ├── capture, stored-image sampling, status, clock and settings
    ├── storage verification, backup and log downloads
    ├── onboard-Wi-Fi uplink selection
    └── NetBird configuration and status
```

`frontend/*.ts` is the only browser source. `tsc` type-checks it in strict mode
and emits `app/static/dist/*.js`, because browsers execute JavaScript. Node is a
build tool only; it is not a deployed server. Flask directly serves the HTML,
generated JavaScript, CSS, API, and health endpoint.

All state-changing API endpoints accept only `POST`. Responses carry
`Content-Security-Policy: default-src 'self'; script-src 'self'; style-src
'self'; img-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'`.

There is no proxy, WSGI wrapper, separate frontend server, redirector,
captive-portal detector, or second diagnostics web server.

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
│   │   └── api.py                    capture, status, clock, backup and NetBird API
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
│   ├── cam_manager.py                Sony discovery, capture and storage owner
│   ├── sony_discovery.py             bounded Sony SDK discovery retries
│   ├── sonySDK_cam.py                Sony SDK camera adapter
│   ├── grf500_altimeter.py           GRF-500 serial protocol and measurement
│   └── unavailable_altimeter.py      non-fabricating GRF-500 failure adapter
├── serial_comms/
│   ├── __init__.py                   Python package marker
│   ├── SerialInterface.py            u-blox connection and reader threads
│   └── SerialProcess.py              NMEA parsing and GPS CSV output
├── support/
│   ├── __init__.py                   Python package marker
│   ├── backup.py                     copy, verification and safe-delete engine
│   ├── basic.py                      observer primitive
│   ├── component_health.py           camera/GPS/altimeter health summary
│   ├── configure.py                  layered default.cfg/initial.cfg reader/writer
│   ├── git_info.py                   deployed revision reporting
│   ├── local_network.py              Flask source-network allow-list
│   ├── rsync_progress.py             live rsync progress-output parser
│   ├── ssd_volume.py                 external USB volume discovery and stable identity
│   └── system_clock.py               phone/GPS clock authority and system-time updates
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
│   ├── test_git_info.py              safe deployed-revision reporting
│   ├── test_grf500_altimeter.py      GRF-500 serial setup and frames
│   ├── test_network_health.py        bounded AP diagnostics and recovery
│   ├── test_recovery_scan.py         rescue scan and NetBird separation
│   ├── test_rsync_progress.py        rsync progress-output parsing
│   ├── test_sony_camera_manager.py   discovered-camera construction
│   ├── test_sony_discovery.py        bounded SDK discovery
│   ├── test_sony_image_format.py     Sony connection and transfer settings
│   ├── test_ssd_volume.py            external USB volume selection
│   ├── test_system_clock.py          phone/GPS clock authority and system-time updates
│   └── test_ublox_gps.py             GPS satellite and quality parsing
├── config.py                         runtime constants and state enums
├── default.cfg                       every supported option: Sony format, capture interval, UI poll rates
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
  message interpretation.
- `Subject` supports the GRF-500 altimeter's observer notifications. It is a
  small shared primitive, not a sensor plugin.
- `TriCapCamsManager` finalises its own capture state: a watcher thread joins
  every camera capture thread and returns the manager to `STOPPED` once those
  threads exit, so no external periodic caller is required.
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
| Retired Sony pipeline support | `sensors/base_setting.py` | Unused settings abstraction removed with the save-thread, preview and tmpfs pipeline |
| IMU | `serial_comms/berryIMU.py`, `serial_comms/IMU.py`, `serial_comms/LIS3MDL.py`, `serial_comms/LSM6DSL.py`, `serial_comms/LSM9DS0.py`, `serial_comms/LSM9DS1.py` | IMU is no longer fitted or consumed |
| Protobuf | `tricap.proto`, `protobuf/**`, `serial_comms/out/**` | Generated protocol layer had no remaining producer or consumer |
| Image geotagging | `support/gps_geotag.py` | Geotagging was too slow and is no longer performed |
| SD-card reader | `SD_card_reader.py` | Unsupported external reader integration |
| GPIO switch and LEDs | `sensors/toggle_switch.py`, `tests/test_gpio_controls.py` | Raspberry Pi `RPi.GPIO` switch/LED path; the Radxa rigs have no switch or LEDs and capture is driven by the browser |
| AssistNow (A-GPS) | `serial_comms/ubloxAgps.py` | GPS is only needed in AP mode, where there is no uplink; the receiver acquires its own fix |
| Session logger | `support/session_logger.py` | Only ever started by the GPIO switch; wrote altimeter lines and log copies to `/home/radxa/temp`, which nothing reads. Altitude is already logged to `altitudeData.csv` for the flight log |
| SMS/phone/Bluetooth-era support | `support/sms_sender.py`, `support/phone_gps.py`, `support/talkbox.py`, `support/connection_monitor.py` | Retired communication paths |
| Replaced clock and path helpers | `support/phone_time.py`, `local_paths.py` | Clock coordination moved to `support/system_clock.py`; deployment paths moved to `config.py` |
| Old image/log models | `support/camera_data.py`, `support/camera_image.py`, `support/log_list.py` | Used only by the retired Flask pages |
| Old Flask UI | `app/forms.py`, `app/views/camera.py`, `app/views/home.py`, `app/views/settings.py`, `app/views/showlog.py`, `app/templates/base.html`, `app/templates/camera/**`, `app/templates/home/**`, `app/templates/settings/**`, `app/templates/showlog/**`, `app/templates/js/**` | Replaced by the two direct Flask operator pages |
| Old browser stack | `app/static/js/**`, old Bootstrap/Bootswatch/Font Awesome/Lato assets under `app/static/css/**` and `app/static/fonts/**`, `app/static/img/default.jpg`, `app/static/img/placeholder.png`, `app/static/img/Power-Shutdown.png` | jQuery and handwritten JavaScript UI replaced by strict TypeScript and one stylesheet |
| Captive portal | `skyseeker-standalone/captive_portal.py`, `services/systemd/skyseeker-portal.service` | Flask now serves the UI directly over the AP |
| System monitors | `support/system_monitor.py`; `RepeatingBarrierPasser` and `PeriodicMonitor` from `support/basic.py`; `SystemMonitor`, `LinuxFreeRAMMonitor`, `LinuxCPUUsageMonitor`, `LinuxDiskUsageMonitor`, `LinuxDiskIOMonitor`, and `SystemMonitorLogger` | duplicate of skyseeker-health journal diagnostics |
| Duplicate diagnostics/recovery | `services/usr-local/bin/skyseeker-diag.py`, `services/usr-local/sbin/skyseeker-ap-monitor`, `services/usr-local/sbin/skyseeker-ap-watchdog`, their systemd units/timers, `udp_ip.sh`, `udp-ip.service` | Consolidated into the dashboard, NetBird and `skyseeker-health` |
| Old launch/deploy files | `tricap.service`, `tricap.ini`, `wsgi.py`, `tricap_launcher.sh`, `tricap_launch_tester.py`, `tricap_loop.py`, `main_serial.py`, `python_setup.sh`, `setup.py`, `wifi_setup.sh`, `get_time_from_camera.sh`, `local_paths_example.py` | Duplicate, obsolete or replaced entry/deployment paths |
| Root artifacts | `.coveragerc`, `defaultend.jpg` | Unused coverage and image residue |
| Root test harnesses | `test_app.py`, `test_behaviour.py`, `test_live_server.py`, `test_sensors.py`, `test_unit.py` | Duplicate and hardware-stale test entry points |
| Replaced clock test | `tests/test_phone_time.py` | Replaced by `tests/test_system_clock.py`, which covers coordinated phone and authoritative GPS time |
| Obsolete tests | `tests/test_alti_simulator.py`, `tests/test_altitude_switch.py`, `tests/test_ap_monitor.py`, `tests/test_ap_watchdog.py`, `tests/test_basic.py`, `tests/test_camera_logger.py`, `tests/test_canon6d_cam.py`, `tests/test_captive_portal.py`, `tests/test_connection_monitor.py`, `tests/test_dummy_alti.py`, `tests/test_dummy_cam.py`, `tests/test_log_list.py`, `tests/test_page_camera_live_server.py`, `tests/test_page_home.py`, `tests/test_page_home_live_server.py`, `tests/test_session_logger.py`, `tests/test_settings.py`, `tests/test_sms_sender.py`, `tests/test_system_monitor.py`, `tests/test_talkbox.py`, `tests/test_trusense_altimeter.py`, `tests/tricap_flask_live_server_test_case.py`, `tests/tricap_flask_test_case.py`, `tests/tricap_tempfile_test_case.py` | Covered retired components, duplicate layers or brittle live-server scaffolding |

The cleanup also removed dead Web and SMS sections, the unused
`session_description` option, and the retired Trusense altimeter options
(`measurement_timeout`, `num_frames_to_avg`) from `default.cfg`; older
`initial.cfg` files are pruned when next saved. It removed the retired `/api`,
`/api/do_preview`, `/api/image`, `/api/stream`, `/api/copy_eta`,
`/api/test_capture`, `/api/lensNumber`, `/api/download_gps_logs`, and
`/api/netbird_key` endpoints, along with the OpenCV, NumPy, Pillow and pytz
dependencies. It also removed unused runtime constants/imports and a captured
AssistNow binary payload that had been committed as a comment.

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
dnsmasq after three failed health checks, with ten minutes between restarts.
Recovery is deferred while `/run/skyseeker-capture-active` exists and is paused
after three restarts without a healthy check. A hidden camera-error reboot path
found during this audit was removed. Reboot remains an explicit operator action
in the setup UI; no monitor, capture callback or timer can invoke it.
