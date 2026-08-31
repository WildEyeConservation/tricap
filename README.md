# SkySeeker

SkySeeker controls the supported aerial-capture hardware and exposes its controls
over the device access point.

Supported hardware:

- Sony cameras through the Sony Camera Remote SDK
- GRF-500 laser altimeter
- u-blox GPS on `/dev/gps`
- TP-Link USB Wi-Fi adapter for the access point
- GPIO capture switch and status LEDs

## Runtime

`tricap.service` starts `tricap.py`, which runs the Flask application on
`127.0.0.1:5000`. `skyseeker-portal.service` serves the operator UI on port 80
and forwards API requests to Flask. The AP, rescue-network scan, diagnostics,
and recovery services are stored under `services/`; see
[`services/README.md`](services/README.md) for installation and operation.

NetBird remains the remote-support path. The rescue scan remains available when
the normal AP path cannot be reached.

## Development

Install the locked Python environment:

```sh
uv sync --locked
```

Install and check the TypeScript frontend:

```sh
npm ci
npm run typecheck
npm run build
```

Run the focused unit tests with Python's `unittest` runner. Hardware-facing code
must still be verified on the target Radxa device with the supported components
connected.
