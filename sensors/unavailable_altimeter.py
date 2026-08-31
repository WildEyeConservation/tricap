"""Non-fatal altimeter placeholder used when configured hardware is absent."""

from config import ALTIMETER_STATE
from support.basic import Subject


class UnavailableAltimeter(Subject):
    """Expose the altimeter interface without inventing sensor readings.

    TriCap historically constructed the configured altimeter while importing the
    Flask app. A disconnected USB sensor therefore prevented the entire control
    service from starting. This placeholder keeps the API and settings surfaces
    operational while clearly reporting that altitude data is unavailable.
    """

    available = False

    def __init__(self, configured_type="grf500", reason="Not connected"):
        super().__init__()
        self.configured_type = configured_type
        self.reason = str(reason or "Not connected")
        self.state = ALTIMETER_STATE.NOT_CONNECTED
        self._measurement = None
        self.value = None
        self.unit = "m"
        self.error = self.reason
        self.error_start = False
        self.config = {}

    @property
    def measurement(self):
        return self._measurement

    def get_state_as_string(self):
        return self.state.name

    def get_error(self):
        return self.error

    def set_error(self, error_code=""):
        self.error = str(error_code or self.reason)

    def get_error_start(self):
        return self.error_start

    def set_error_start(self, error_code):
        self.error_start = error_code

    def start_measuring(self):
        # Missing hardware remains a passive, non-fatal state.
        self.state = ALTIMETER_STATE.NOT_CONNECTED
        return False

    def stop_measuring(self):
        self.state = ALTIMETER_STATE.NOT_CONNECTED

    def disconnect(self):
        self.state = ALTIMETER_STATE.NOT_CONNECTED
