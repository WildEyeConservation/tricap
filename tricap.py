""" D Joubert Innoventix Consulting 27 October 2016
    The main run file for tricap. Based on the typical flask app main file template.
"""

from app import app

# For quick testing on the same computer
# if __name__ == '__main__':
#     app.run(debug=True, use_reloader=False)

# If you need to specify the host and port address, so that website is accessible through LAN
app.run(debug=True, use_reloader=False, host="0.0.0.0", port=5000)
