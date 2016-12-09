"""Keeps a list of msgs from whatever was logged."""

import logging


class ListHandler(logging.Handler):
    """A logging handlers which stores log records to a limited size list."""

    def __init__(self, max_msg_count):
        """Constructor."""
        logging.Handler.__init__(self)

        self._max_msg_count = max_msg_count
        self.records = []

    def emit(self, record):
        """Save the message to the list."""
        self.records.append(record)

        if len(self.records) > self._max_msg_count:
            self.records = self.records[-self._max_msg_count:]


class LogListAccessor():
    """Provides access to the last couple of log messages."""

    def __init__(self, max_msg_count):
        """Constructor."""
        # Instantiate a ListHandler which only records error messages
        self._handler = ListHandler(max_msg_count)
        self._handler.setFormatter(logging.Formatter("%(message)s"))
        self._handler.setLevel(logging.ERROR)

        # Couple this to the root logger
        logging.getLogger('').addHandler(self._handler)

    def get_msgs(self):
        """Get the messages from the ListHandler records."""
        return [record.getMessage() for record in self._handler.records]
