"""Talkbox - Allow clients to post messages."""

import logging
from enum import IntEnum

TALK_REPLY = IntEnum("TalkReply", ["YES", "NO", "UNANSWERED"])


class TalkMsg():
    """TalkBox message object."""

    def __init__(self, msg='', reply=TALK_REPLY.UNANSWERED):
        """Constructor, with msg and reply optional arguments."""
        self.msg = msg
        self.reply = reply


class LockList(list):
    """LockList - A thread-safe list with locking.

    Refer to http://effbot.org/pyfaq/what-kinds-of-global-value-mutation-are-thread-safe.htm
    """

    def __init__(self, lock, init_list=None):
        """Constructor."""
        super().__init__()
        self._lock = lock
        if init_list is not None:
            for item in init_list:
                self.append(item)

    def __setitem__(self, key, value):
        """Call the list setitem, but with locking."""
        with self._lock:
            super().__setitem__(key, value)

    def append(self, value):
        """Append, but with locking."""
        with self._lock:
            super().append(value)

    def remove(self, value):
        """Remove, but with locking."""
        with self._lock:
            super().remove(value)


class LimitedLockList(LockList):
    """LimitedLockList - A LockList, but with a limited number of entries."""

    def __init__(self, lock, max_entries, init_list=None):
        """Constructor."""
        self._max_entries = max_entries
        super().__init__(lock, init_list=init_list)

    def append(self, value):
        """Append, but with limiting the number of entries."""
        super().append(value)
        while len(self) > self._max_entries:
            self.remove(self[0])


class TalkBox():
    """Provide means of recording a limited number of messages."""

    _root_logger = logging.getLogger(__name__)

    def __init__(self, lock, max_msg_count, init_list=None):
        """Constructor."""
        self._lock = lock
        self._max_msg_count = max_msg_count
        self.talk_msgs = LimitedLockList(self._lock, self._max_msg_count, init_list=init_list)

    def clear(self):
        """Clear away all messages."""
        self.talk_msgs = LimitedLockList(self._lock, self._max_msg_count)

    def add_message(self, msg, reply=TALK_REPLY.UNANSWERED):
        """Add a message to the record."""
        self.talk_msgs.append(TalkMsg(msg, reply))

    def _convert_reply_code(self, reply_code):
        for reply in TALK_REPLY:
            if reply_code == reply:
                return reply

    def change_reply(self, msg, new_reply_code):
        """Change the reply associated with a message."""
        msgs = [tm.msg for tm in self.talk_msgs]

        if msg not in msgs:
            self._root_logger.warning('Could not find %s in list of talks.', msg)
        else:
            talk_msg = self.talk_msgs[msgs.index(msg)]
            talk_msg.reply = self._convert_reply_code(new_reply_code)
            self.talk_msgs[msgs.index(msg)] = talk_msg
