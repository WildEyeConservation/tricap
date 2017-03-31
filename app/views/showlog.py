import os

from flask import Blueprint, render_template, request, jsonify

from app import rootlogger

from config import SERVER_LOG_DIR

showlog_bp = Blueprint('showlog', __name__)


class LogFormatter:
    def __init__(self, log_fp):
        self._log_fp = log_fp

    def format_log(self, log_code):
        log = ''

        with open(self._log_fp) as log_file:
            loglines = log_file.readlines()

            for line in loglines:
                try:
                    linesections = line.split('|')
                    # reduced date
                    log += linesections[0][5:18]
                    # reduced filename
                    log += ' | ' + '<font color="blue">' + linesections[1].split('/')[-1] + '</font>'
                    # function name
                    log += ' | ' + linesections[2]
                    # log message level
                    log += ' | ' + '<font color="green">' + linesections[3] + '</font>'
                    # messsage
                    log += ' | ' + linesections[4]
                    log += '<br />'
                except IndexError:
                    # This happens when a log line does not have the expected number of sections. When we drop through
                    # to here we shoul allready have printed everything we have. so simply ignore and continue
                    pass

        return log


@showlog_bp.route('/showlog', methods=['GET'])
def showlog():
    rootlogger.info('ShowLog Page Requested.')
    return render_template('/showlog/showlog.html')


@showlog_bp.route('/_get_log', methods=['GET'])
def provide_log():
    log_code = request.args.get('logCode', 0, type=int)

    log_formatter = LogFormatter(os.path.join(SERVER_LOG_DIR, 'tricap_master.log'))
    log = log_formatter.format_log(log_code)

    data = {'log': log}

    return jsonify(data)
