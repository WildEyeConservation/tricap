"""The main run file for tricap. Based on the typical flask app main file template."""

from support.usb_storage_mode import recover_usb_storage_mode

# A service restart after an interrupted storage job must restore USB devices
# before camera, GPS and altimeter discovery begins.
recover_usb_storage_mode()

from app import app

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False, host="0.0.0.0", port=5000, passthrough_errors=True)

