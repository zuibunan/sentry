from __future__ import absolute_import

__all__ = ('EventState',)


class EventState(object):
    UNKNOWN = object()

    def __init__(self, is_new=UNKNOWN, is_regression=UNKNOWN,
                 is_sample=UNKNOWN):
        self.is_new = is_new
        self.is_regression = is_regression
        self.is_sample = is_sample
