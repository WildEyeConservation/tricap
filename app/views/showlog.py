import os

from flask import Blueprint, render_template, send_file, request, jsonify

from config import SERVER_LOG_DIR, LOG_CODES

showlog_bp = Blueprint('showlog', __name__)


class LogFormatter():
    def __init__(self, log_fp):
        self._log_fp = log_fp

    def format_log(self, log_code):
        log = ''

        with open(self._log_fp) as log_file:
            loglines = log_file.readlines()

            for line in loglines:
                linesections = line.split('|')
                log += linesections[0][5:18] # reduced date
                log += ' | ' + '<font color="blue">' + linesections[1].split('/')[-1] + '</font>'# reduced filename
                log += ' | ' + linesections[2] # function name
                log += ' | ' + '<font color="green">'+ linesections[3] + '</font>'# log message level
                log += ' | ' + linesections[4] # messsage
                log += '<br />'

        return log

# TODO Set time correctly on overall logger

@showlog_bp.route('/showlog', methods=['GET'])
def showlog():
    return render_template('/showlog/showlog.html')

@showlog_bp.route('/_get_log', methods=['GET'])
def provide_log():
    log_code = request.args.get('logCode', 0, type=int)

    log_formatter = LogFormatter(os.path.join(SERVER_LOG_DIR, 'tricap_server.log'))
    log = log_formatter.format_log(log_code)

    data = {'log': log}

    return jsonify(data)
