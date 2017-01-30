"""The basics of basic classes. Should be so abstract as to do nothing."""

import threading

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
            pass

    def notify(self, modifier=None):
        """Update all of the observers, except for the observer doing the update."""
        for observer in self._observers:
            if modifier != observer:
                observer.update(self)


class RepeatingBarrierPasser(threading.Thread):
    """
    A thread object that passes a threading barrier every x seconds.

    Serves as a timing mechanism for synchronised threads that also use the barrier.

    Source:
    stackoverflow.com/questions/12435211/python-threading-timer-repeat-function-every-n-seconds.
    """

    def __init__(self, repeat_rate: float, stop_event: threading.Event, barrier: threading.Barrier):
        """Initialise a timing mechanism to repeat every repeat_rate seconds."""
        threading.Thread.__init__(self)
        self._stop_event = stop_event
        self._barrier = barrier
        self._repeat_rate = repeat_rate

    def run(self):
        """Do not invoke this function directly, begin the timer by calling start."""
        while not self._stop_event.wait(self._repeat_rate):
            self._barrier.wait()
