"""SMS sender - a periodic sender of messages.

We need a periodic sender, but also something that can send on demand.
"""

import logging

from urllib.request import urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError

from support.configure import TricapConfig

from .basic import PeriodicMonitor
import os


class SMSSender(object):
    """Send sms through http request to SMSGateway, running on configured ip."""

    def __init__(self):
        """Constructor, reads params from the configure file."""
        super(SMSSender, self).__init__()
        config = TricapConfig()
        self.ip = config.get('ip', TricapConfig.SMS_SECTION_HEADER)
        self.number = config.get('number', TricapConfig.SMS_SECTION_HEADER)
        self.pwd = config.get('pwd', TricapConfig.SMS_SECTION_HEADER)
        self.timeout = config.get('timeout', TricapConfig.SMS_SECTION_HEADER,
                                  type_str=TricapConfig.TYPE_FLOAT)

    def check_response(self, response):
        """Return true if the response is good, false if the reponse is bad."""
        lines = response.readlines()
        # if lines[2] == b'Mesage SENT!<br/>\n':
        if b'Mesage SENT' in lines[2]:  # Keep as Mesage
            # print("Message sent successfully")
            return True
        else:
            # Not sure if we can ever reach this
            logging.getLogger('').warning("SMSGateway did not successfully send sms: %s", lines)
            return False

    def send(self, msg):
        """Send a message through the http request, return success flag."""
        gw = os.popen("ip -4 route show default").read().split('\n') # possibly eth and wlan0
        ip = ''
        for interface in gw:
            if 'wlan0' in interface:
                ip = interface.split()[2]

        if ip == '':
            ip = self.ip
        args = urlencode({'phone': self.number, 'text': msg, 'password': self.pwd})
        sms_url = 'http://%s:9090/sendsms?%s' % (ip, args)
        try:
            # TODO: The use of a timeout is a short term fix. SMSSender should use a separate
            # thread to send sms, to prevent the system from hanging if it struggles to send the
            # message.
            return self.check_response(urlopen(sms_url, timeout=self.timeout))
        except HTTPError:
            logging.getLogger('').warning("SMS not sent, http error (bad arguments?).")
            return False
        except URLError:
            logging.getLogger('').warning("SMS not sent, url error (is SMS gateway running?)")
            return False


class SMSObserver():
    """An observer which sends an sms on the primary PeriodicMonitors update.

    Hooks up to a primary periodic monitor and optionally other secondary monitors.
    On each of the updates of the secondary monitors, a msg is filled with the desired values.
    When the primary monitor updates, it sends the sms.
    """

    def __init__(self, prime_monitor, sec_monitors=None, send_on_start=False):
        """Constructor."""
        self.sender = SMSSender()

        self.prime_monitor = prime_monitor

        self.msg = ''

        prime_monitor.attach(self)

        if sec_monitors:
            if type(sec_monitors) is not list:
                sec_monitors = [sec_monitors]

            for mon in sec_monitors:
                if mon is not None:
                    mon.attach(self)

        if send_on_start:
            self.sender.send('TriCap SMS Sender Activated.')

    def update(self, monitor):
        """Update method called by monitor subject."""
        val = str(monitor.value)
        logging.getLogger('').debug("update SMS {} {}".format(val, self.msg))

        if monitor == self.prime_monitor:
            self.msg = monitor.type_id + ' : ' + val + self.msg
            if self.sender.send(self.msg):
                logging.getLogger('').debug('Sent sms : %s', self.msg)
            else:
                logging.getLogger('').warning('Failed to send sms : %s', self.msg)
            self.msg = ''
        else:
            self.msg = self.msg + ', ' + monitor.type_id + ' : ' + val
