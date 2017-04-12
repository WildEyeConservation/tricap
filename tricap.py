"""The main run file for tricap. Based on the typical flask app main file template."""

from app import app

if __name__ == "__main__":
    app.run(debug=False, use_reloader=False, host="0.0.0.0", port=5000, passthrough_errors=True)
