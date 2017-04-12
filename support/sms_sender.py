"""SMS sender - a periodic sender of messages.

We need a periodic sender, but also something that can send on demand.
"""

import logging

from urllib.request import urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError

from support.configure import TricapConfig


class SMSSender(object):
    """Send sms through http request to SMSGateway, running on configured ip."""

    def __init__(self):
        """Constructor, reads params from the configure file."""
        super(SMSSender, self).__init__()
        config = TricapConfig()
        self.ip = config.get('ip', TricapConfig.SMS_SECTION_HEADER)
        self.number = config.get('number', TricapConfig.SMS_SECTION_HEADER)
        self.pwd = config.get('pwd', TricapConfig.SMS_SECTION_HEADER)

    def check_response(self, response):
        """Return true if the response is good, false if the reponse is bad."""
        lines = response.readlines()
        if lines[2] == b'Mesage SENT!<br/>\n':
            return True
        else:
            # Not sure if we can ever reach this
            logging.getLogger('').warning("SMSGateway did not succesfully send sms: %s", lines)
            return False

    def send(self, msg):
        """Send a message through the http request, return success flag."""
        args = urlencode({'phone': self.number, 'text': msg, 'password': self.pwd})
        sms_url = 'http://%s:9090/sendsms?%s' % (self.ip, args)
        try:
            return self.check_response(urlopen(sms_url))
        except HTTPError:
            logging.getLogger('').warning("SMS not sent, bad request.")
            return False


class SMSPeriodicSender():
    """Send sms via http request at a constant rate.

    At its most simplest it should send the current time.
    Should subscribe to various loggers and send additional info?
    """

    pass
