"""Small, dependency-free helpers for Sony SDK camera discovery."""

import time


def discover_sony_cameras(camera_factory, attempts=15, interval=2.0,
                          stable_results=1, logger=None):
    """Return ``(sdk, count)`` after retrying transient empty/error results.

    USB cameras can finish enumerating after the application service starts.
    A fresh SDK instance is used for each attempt so its device list cannot be
    stuck on the empty snapshot taken by an earlier instance.
    """
    attempts = max(1, int(attempts))
    stable_results = max(1, int(stable_results))
    last_error = None
    last_count = 0
    stable_count = 0

    for attempt in range(1, attempts + 1):
        sdk = None
        try:
            sdk = camera_factory()
            camera_count = sdk.getNumCameras()
            if camera_count > 0:
                if camera_count == last_count:
                    stable_count += 1
                else:
                    last_count = camera_count
                    stable_count = 1
                if stable_count >= stable_results:
                    return sdk, camera_count
                last_error = RuntimeError(
                    "Sony SDK camera count {} is not stable yet".format(
                        camera_count
                    )
                )
            else:
                last_count = 0
                stable_count = 0
                last_error = RuntimeError("Sony SDK reported zero cameras")
        except Exception as exc:
            last_count = 0
            stable_count = 0
            last_error = exc

        if logger is not None:
            logger.warning(
                "Sony camera discovery attempt %s/%s failed: %s",
                attempt,
                attempts,
                last_error,
            )

        # Release an SDK instance which may have cached an incomplete USB
        # device list before constructing the next one.
        if sdk is not None:
            del sdk

        if attempt < attempts:
            time.sleep(interval)

    raise RuntimeError(
        "No Sony cameras became available after {} discovery attempts".format(
            attempts
        )
    ) from last_error
