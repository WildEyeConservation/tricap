"""Run the SkySeeker web interface and capture controller."""

import signal

from app import app, shutdown

if __name__ == "__main__":
    def handle_sigterm(_signum, _frame):
        shutdown()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, handle_sigterm)
    app.run(host="0.0.0.0", port=80, debug=False, use_reloader=False, threaded=True)

