# D Joubert Innoventix Consulting 27 October 2016
# The main run file for mocup

from app import app

# if __name__ == '__main__':
#     app.run(debug=True, use_reloader=False)

# If you need to specify the host and port address:
app.run(debug=True, use_reloader=False, host="0.0.0.0", port=5000)
