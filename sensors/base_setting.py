import numbers
from collections import namedtuple

SettingSpec = namedtuple('SettingSpec', 'get_value set_value choices')


class BaseSetting:
    class SettingException(Exception):
        pass

    def __init__(self, widget):
        self._widget = widget

    def __repr__(self):
        return str(self._widget.get_value())

    def __ne__(self, other):
        if isinstance(other, numbers.Number):
            return float(self._widget.get_value()) != other
        return self._widget.get_value().__ne__(str(other))

    def __eq__(self, other):
        if isinstance(other, numbers.Number):
            return float(self._widget.get_value()) == other
        return self._widget.get_value().__eq__(str(other))

    def __lt__(self, other):
        if isinstance(other, numbers.Number):
            return float(self._widget.get_value()) < other
        return self._widget.get_value().__lt__(str(other))

    def __gt__(self, other):
        if isinstance(other, numbers.Number):
            return float(self._widget.get_value()) > other
        return self._widget.get_value().__gt__(str(other))

    def __le__(self, other):
        if isinstance(other, numbers.Number):
            return float(self._widget.get_value()) <= other
        return self._widget.get_value().__le__(str(other))

    def __ge__(self, other):
        if isinstance(other, numbers.Number):
            return float(self._widget.get_value()) >= other
        return self._widget.get_value().__ge__(str(other))

    def set(self, value):
        datatype = type(self._widget.get_value())
        value = datatype(value)
        # value = str(value)
        if self.choices and value not in self.choices:
            raise BaseSetting.SettingException(
                "%s is not a valid value for %s. Valid choices are : %s" % (value, self._widget.name, self.choices))
        self._widget.set_value(value)
        # print('Setting %s to %s', self._widget.name, str(value))
        # print(self._widget.name, ' is ', self._widget.get_value())

    @property
    def choices(self):
        return self._widget.choices
