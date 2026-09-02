"""The basics of basic classes. Should be so abstract as to do nothing."""

import logging

from abc import ABCMeta


class Subject(object):
    """Abstract base class for observable objects (implementing the observer design pattern)."""

    __metaclass__ = ABCMeta

    def __init__(self):
        """Constructor."""
        self._observers = []

    def attach(self, observer):
        """Attach observer to list of observers."""
        if observer not in self._observers:
            self._observers.append(observer)

    def detach(self, observer):
        """Detach the observer from the list."""
        try:
            self._observers.remove(observer)
        except ValueError:
            logging.getLogger('root').warning('Subject asked to detach non-existent observer : %s',
                                              str(observer))
            pass

    def notify(self, modifier=None):
        """Update all of the observers, except for the observer doing the update."""
        for observer in self._observers:
            if modifier != observer:
                observer.update(self)
