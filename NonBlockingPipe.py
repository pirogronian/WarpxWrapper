
import threading
import queue
import time

class NonBlockingPipe:
    def __init__(self, Input = None):
        self.ExitOnEmpty = True
        self.Interval = 2
        self.Queue = queue.Queue()
        self.Input = Input
        self.Thread = threading.Thread(target=NonBlockingPipe.Daemon, args=(self,), daemon = True)

    def Daemon(self):
        print(f"Deamon started. Activity status: {self.IsActive()}")
        while 1:
            line = self.Input.readline()
#            print("   Got line of data.")
            if line == "":
                if self.ExitOnEmpty:
#                    print("   Input empty, exiting.")
                    break
                else:
#                    print("   Input empty, waiting.")
                    time.sleep(self.Interval)
                    continue
#            print("Put data to queue.")
            self.Queue.put_nowait(line)

    def Activate(self, Input = None):
        if Input != None:
            self.Input = Input
        self.Thread.start()

    def IsActive(self):
        return self.Thread.is_alive()

    def Read(self):
        if not self.Queue.empty():
            return self.Queue.get_nowait()

