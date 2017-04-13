"""Test the sms senders."""

import time

from .tricap_tempfile_test_case import TriCapTempFilerTestCase

from support.basic import TimeMonitor
from support.sms_sender import SMSSender, SMSObserver
from support.configure import TricapConfig


class SMSSenderDeviceTests(TriCapTempFilerTestCase):
    """Test the sms senders."""

    def test_sms_sender(self):
        """Test the SMSSender."""
        sms_sender = SMSSender()
        test_msg = 'Test Message 123.'
        self.assertEqual(sms_sender.send(test_msg), True)
        print('Please check that you have received an sms stating: %s' % test_msg)

    def test_bad_sms(self):
        """Test the SMSSender."""
        config = TricapConfig()
        section_dict = config.get_section_dict(TricapConfig.SMS_SECTION_HEADER)
        section_dict['pwd'] = 'BADDPASSWORD'
        config.set_section(section_dict, TricapConfig.SMS_SECTION_HEADER)
        config.save_to_file()

        sms_sender = SMSSender()
        test_msg = 'Bad Message'
        self.assertEqual(sms_sender.send(test_msg), False)
        print('Please check that you have did not receive a sms stating: %s' % test_msg)


class SMSObserverDeviceTests(TriCapTempFilerTestCase):
    """test the sms observer."""

    def test_sms_observer(self):
        """Test the sms observer."""
        time_mon1 = TimeMonitor(0.05)
        time_mon2 = TimeMonitor(0.06)
        time_mon3 = TimeMonitor(0.07)

        mons = [time_mon1, time_mon2, time_mon3]

        sms_obs = SMSObserver(time_mon3, [time_mon1, time_mon2])

        for mon in mons:
            mon.start()

        time.sleep(0.08)

        for mon in mons:
            mon.stop()

        time.sleep(1)

        print("Please check that you did recieve a message with 3 time stamps in it.")

        # check that the to send msg is at least blank
        self.assertEqual(sms_obs.msg, '')
