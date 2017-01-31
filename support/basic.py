"""The basics of basic classes. Should be so abstract as to do nothing."""

import threading

from abc import ABCMeta, abstractmethod


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

    def __init__(self, repeat_rate: float, stop_event: threading.Event, barrier: threading.Barrier,
                 daemon: bool = False):
        """Initialise a timing mechanism to repeat every repeat_rate seconds."""
        threading.Thread.__init__(self, daemon=daemon)
        self._stop_event = stop_event
        self._barrier = barrier
        self._repeat_rate = repeat_rate

    def run(self):
        """Do not invoke this function directly, begin the timer by calling start."""
        while not self._stop_event.wait(self._repeat_rate):
            self._barrier.wait()


class UnknownOperatingSystem(Exception):
    """Exception for when os.name returns an unkown operating system id."""

    pass


class PeriodicMonitor(Subject):
    """A subject that periodically checks something and updates the observers."""

    __metaclass__ = ABCMeta

    def __init__(self, period):
        """Constructor."""
        super(PeriodicMonitor, self).__init__()

        self.period = period

        self._stop_event = None
        self._barrier = None
        self._period_timer = None

    def __del__(self):
        """Destructor."""
        self.stop()

    @abstractmethod
    def monitor_step(self):
        """Check up on whatever is monitored."""
        pass

    def monitor(self):
        """In a loop, check the network connection."""
        while True:
            if self._stop_event.is_set():
                return
            self._barrier.wait()
            self.monitor_step()
            self.notify()

    def start(self):
        """Start the network monitoring in separate threads."""
        self._stop_event = threading.Event()
        self._barrier = threading.Barrier(2)  # one for the timer, one for the status checking
        self._period_timer = RepeatingBarrierPasser(self.period,
                                                    self._stop_event, self._barrier, daemon=True)
        thread = threading.Thread(target=self.monitor, daemon=True)
        self._period_timer.start()
        thread.start()

    def stop(self):
        """Stop the threads involved in the montoring."""
        self._stop_event.set()
