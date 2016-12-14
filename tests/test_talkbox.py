"""Unittest for the TalkBox class."""

import logging
import unittest
import os
import pdb

from testfixtures import LogCapture
from threading import Lock

from support.talkbox import TalkBox, TALK_REPLY, TalkMsg

from config import SERVER_LOG_DIR


class TestTalkBox(unittest.TestCase):
    """Class containing the tests for the tallkbox."""

    # setup a logging tool for the talkbox module specifically
    format_str = "%(asctime)s | %(pathname)s:%(lineno)d | %(funcName)s | %(levelname)s | %(message)s "
    handler = logging.FileHandler(filename=os.path.join(SERVER_LOG_DIR, 'test_talkbox.log'))
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter(format_str))
    handler.addFilter(logging.Filter(name='app.views.talkbox'))
    rootLogger = logging.getLogger('')
    rootLogger.addHandler(handler)
    rootLogger.setLevel(logging.DEBUG)

    def setUp(self):
        """Set up the tests. Not bothering to backup the message log."""
        self.lock = Lock()

    def tearDown(self):
        """Stuff to do after a test  has finished."""
        pass

    def test_init_with_list(self):
        """Test initialisation with a list of messages."""
        tlist = [TalkMsg('test1'), TalkMsg('test2'), TalkMsg('test3')]
        talkbox = TalkBox(self.lock, 3, init_list=tlist)

        self.assertEqual(talkbox.talk_msgs[0].msg, tlist[0].msg)
        self.assertEqual(talkbox.talk_msgs[1].msg, tlist[1].msg)
        self.assertEqual(talkbox.talk_msgs[2].msg, tlist[2].msg)

    def test_add_message(self):
        """Test to see if we can add a message to the TalkBox."""
        talkbox = TalkBox(self.lock, 5)
        talkbox.add_message('Test Message')

        self.assertEqual(len(talkbox.talk_msgs), 1)
        self.assertEqual(talkbox.talk_msgs[0].msg, 'Test Message')
        self.assertEqual(talkbox.talk_msgs[0].reply, TALK_REPLY.UNANSWERED)

        talkbox.add_message('Another Message', 1)

        self.assertEqual(len(talkbox.talk_msgs), 2)
        self.assertEqual(talkbox.talk_msgs[1].msg, 'Another Message')
        self.assertEqual(talkbox.talk_msgs[1].reply, TALK_REPLY.YES)

    def test_clear(self):
        """Test if the talkbox really empties the text file."""
        talkbox = TalkBox(self.lock, 5)
        talkbox.add_message('Test Message')
        talkbox.add_message('Another Message', 1)
        talkbox.add_message('Another Message', 2)
        talkbox.add_message('Test Message')
        talkbox.add_message('Test Message')
        talkbox.clear()

        self.assertEqual(len(talkbox.talk_msgs), 0)

    def test_max_size(self):
        """Test if the talkbox only keeps the last X messages."""
        talkbox = TalkBox(self.lock, 3)
        talkbox.add_message('Message 1')
        talkbox.add_message('Message 2', 1)
        talkbox.add_message('Message 3', 2)
        talkbox.add_message('Message 4')
        talkbox.add_message('Message 5')

        self.assertEqual(len(talkbox.talk_msgs), 3)
        self.assertEqual(talkbox.talk_msgs[0].msg, 'Message 3')
        self.assertEqual(talkbox.talk_msgs[1].msg, 'Message 4')
        self.assertEqual(talkbox.talk_msgs[2].msg, 'Message 5')

    def test_changing_a_reply(self):
        """Test if the talkbox can change the reply to a stored message."""
        talkbox = TalkBox(self.lock, 3)
        talkbox.add_message('Test Message First')
        talkbox.add_message('Test Message Second')
        talkbox.add_message('Test Message Third')

        talkbox.change_reply('Test Message Second', TALK_REPLY.YES.value)
        talkbox.change_reply('Test Message Third', TALK_REPLY.NO.value)

        self.assertEqual(talkbox.talk_msgs[1].reply, TALK_REPLY.YES, msg=None)
        self.assertEqual(talkbox.talk_msgs[2].reply, TALK_REPLY.NO, msg=None)

    def test_changing_non_existent_message(self):
        """Test if the talkbox reacts correctly when trying to change non-existant message."""
        talkbox = TalkBox(self.lock, 3)
        talkbox.add_message('Test Message First')
        talkbox.add_message('Test Message Second')
        talkbox.add_message('Test Message Third')

        with LogCapture() as lc:
            talkbox.change_reply('Test Message Fourth', TALK_REPLY.YES.value)
            lc.check(('support.talkbox', 'WARNING',
                      'Could not find Test Message Fourth in list of talks.'))

# TODO Write a unittest simulating multiple clients using the talkbox to communicate
