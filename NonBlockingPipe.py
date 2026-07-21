
import enum
import os
import fcntl
import threading
import queue
import time

class NonBlockingPipe:
    class Mode:
        BYTES = 1


    def __init__(self, Input = None):
        self.ExitOnEmpty = True
        self.Interval = 2
        self.Queue = queue.Queue()
        self.Input = Input
        self.Thread = threading.Thread(target=NonBlockingPipe.Daemon, args=(self,), daemon = True)

    def DisableBlocking(self):
        fd = self.Input.fileno()
        Flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, Flags | os.O_NONBLOCK)

    def EnableBlocking(self):
        fd = self.Input.fileno()
        Flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, Flags & ~os.O_NONBLOCK)

    def DirectRead(self):
        return self.Input.readline()

    def Daemon(self):
#        print(f"Deamon started. Activity status: {self.IsActive()}")
        while 1:
            data = self.DirectRead()
#            print("   Got line of data.")
            if len(data) == 0:
                if self.ExitOnEmpty:
#                    print("   Input empty, exiting.")
                    break
                else:
#                    print("   Input empty, waiting.")
                    time.sleep(self.Interval)
                    continue
#            print("Put data to queue.")
#            print("Got data: ", data)
            self.Queue.put_nowait(data)

    def Activate(self, Input = None):
        if Input != None:
            self.Input = Input
        self.Thread.start()

    def IsActive(self):
        return self.Thread.is_alive()

    def Empty(self):
        return self.Queue.empty()

    def Read(self):
        if not self.Queue.empty():
            ret = self.Queue.get_nowait()
#            if hasattr(self, "old_settings"):
#                print("Read: ", ret)
            return ret

