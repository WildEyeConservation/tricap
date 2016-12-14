"""Testing the log list accessor."""

import unittest
import logging

from support.log_list import LogListAccessor


class TestLogList(unittest.TestCase):
    """docstring for TestLogList."""

    root_logger = logging.getLogger('')

    def test_making_and_getting_error_msgs(self):
        """Check that when we make error messages, we can access them."""
        log_list = LogListAccessor(3)

        self.root_logger.error('Test Message 1')
        self.root_logger.error('Test Message 2')
        self.root_logger.error('Test Message 3')

        msgs = log_list.get_msgs()
        self.assertEqual(len(msgs), 3)
        self.assertEqual(msgs[0], 'Test Message 1')
        self.assertEqual(msgs[1], 'Test Message 2')
        self.assertEqual(msgs[2], 'Test Message 3')

    def test_exceeding_the_number_of_msgs(self):
        """Check that only the correct number of messages are stored and that they are cycled."""
        log_list = LogListAccessor(3)

        self.root_logger.error('Test Message 1')
        self.root_logger.error('Test Message 2')
        self.root_logger.error('Test Message 3')
        self.root_logger.error('Test Message 4')
        self.root_logger.error('Test Message 5')

        msgs = log_list.get_msgs()
        self.assertEqual(len(msgs), 3)
        self.assertEqual(msgs[0], 'Test Message 3')
        self.assertEqual(msgs[1], 'Test Message 4')
        self.assertEqual(msgs[2], 'Test Message 5')
