
import time

class Timer:
    Timeout = 0

    def __init__(self, Timeout = 0):
        self.Start = time.time()
        self.Timeout = Timeout

    def Reset(self):
        self.Start = time.time()

    def Elapsed(self):
        return time.time() - self.Start

    def Expired(self):
        return self.Elapsed() > self.Timeout
