"""Test the sms senders."""

from .tricap_tempfile_test_case import TriCapTempFilerTestCase

from support.sms_sender import SMSSender
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
