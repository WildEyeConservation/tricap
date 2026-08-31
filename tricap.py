"""Run the SkySeeker web interface and capture controller."""

from app import app

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80, debug=False, use_reloader=False, threaded=True)

