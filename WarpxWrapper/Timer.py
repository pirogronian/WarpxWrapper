
import time

from WarpxWrapper import Config
from .Various import INF

class Timer:
    Timeout = 0.0

    def __init__(self, Timeout = 0.0):
        self.Start = -INF
        self.Timeout = Timeout

    def GetTimeout(self):
        t = type(self.Timeout)
        if t == float or t == int:
            return self.Timeout
        return getattr(Config, self.Timeout)

    def Reset(self):
        self.Start = time.time()

    def Elapsed(self):
        return time.time() - self.Start

    def Expired(self):
        return self.Elapsed() > self.GetTimeout()
