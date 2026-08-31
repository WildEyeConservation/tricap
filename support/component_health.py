"""Build a stable, JSON-friendly view of optional rig component health."""


def _entry(connected, message, **extra):
    value = {
        'connected': bool(connected),
        'state': 'connected' if connected else 'not_connected',
        'message': message,
    }
    value.update(extra)
    return value


def component_health(camera_manager, gps, altimeter, storage_mounted):
    """Return component availability without probing or changing hardware."""
    try:
        camera_count = len(camera_manager.get_cameras_as_list() or [])
    except Exception:
        camera_count = 0
    camera_startup_error = str(
        getattr(camera_manager, 'camera_startup_error', '') or ''
    )

    gps_connected = bool(getattr(gps, 'isConnected', False))
    gps_fix = False
    try:
        gps_fix = bool(gps.hasGps())
    except Exception:
        pass

    altimeter_connected = bool(getattr(altimeter, 'available', False))
    return {
        'cameras': _entry(
            camera_count > 0,
            (f'{camera_count} camera' + ('' if camera_count == 1 else 's') + ' connected.')
            if camera_count
            else (
                'Cameras are not connected. Storage operations remain '
                'available. Restart Tricap after reconnecting cameras. '
                f'Last error: {camera_startup_error}'
                if camera_startup_error
                else 'No cameras connected. Capture is unavailable.'
            ),
            count=camera_count,
            error=camera_startup_error),
        'gps': _entry(
            gps_connected,
            ('GPS connected with a position fix.' if gps_fix else 'GPS connected; waiting for a position fix.')
            if gps_connected else 'GPS is not connected. Capture can continue without location data.',
            fix=gps_fix),
        'altimeter': _entry(
            altimeter_connected,
            'GRF-500 altimeter connected.' if altimeter_connected
            else 'GRF-500 altimeter is not connected. Capture can continue without altitude data.'),
        'storage': _entry(
            storage_mounted,
            'Internal storage mounted.' if storage_mounted
            else 'Internal storage is not mounted. Check storage before capturing.'),
    }
