
import os
import sys
import fcntl
import threading
import queue
import time
import blessed

class CommonStream:
    Interval = 0.0
    QueueSizeThreshold = 0

    def __init__(self, Stream = None, EventQueue = None, Event = True):
        self.Queue = queue.SimpleQueue()
        self.Stream = Stream
#        print("Got event queue with value: ", EventQueue)
        self.EventQueue = EventQueue
        self.Event = Event

    def Activate(self, Stream = None):
        if Stream != None:
            self.Stream = Stream
        self.Thread = threading.Thread(target=self.Daemon, daemon = True)
        self.Thread.start()

    def IsActive(self):
        return self.Thread.is_alive()

    def DisableBlocking(self):
        fd = self.Stream.fileno()
        Flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, Flags | os.O_NONBLOCK)

    def EnableBlocking(self):
        fd = self.Stream.fileno()
        Flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, Flags & ~os.O_NONBLOCK)

    def HasData(self):
        return self.Queue.empty()

    def QueueSize(self):
        return len(self.Queue)

    def DataSize(self):
        return self.Queue.qsize()

    def SendEvent(self):
        if self.EventQueue == None:
#            print("No even queue!")
            return
#        print(f"Checking threshold: {self.Queue.qsize()} > {self.QueueSizeThreshold}.")
        if self.Queue.qsize() > self.QueueSizeThreshold:
            self.EventQueue.put_nowait(self.Event)
#            self.EventQueue.put_nowait(time.time())
#            print(f"Send event {self.Event} from stream.")

class InputStream(CommonStream):

    def DirectRead(self):
        return self.Stream.read()

    def Daemon(self):
#        print("Self given:", self)
#        print("An extra argument given:", extra)
#        print(f"Deamon started. Activity status: {self.IsActive()}")
        while 1:
            data = self.DirectRead()
#            print("   Got line of data.")
            if len(data) == 0:
                if self.Interval == 0:
#                    print("   Input empty, exiting.")
                    break
                else:
#                    print(f"   Input empty, waiting for {self.Interval}.")
                    time.sleep(self.Interval)
                    continue
#            print("Got data:", data)
#            print("Put data to queue.")
#            print("Got data: ", data)
            self.Queue.put_nowait(data)
            self.SendEvent()

    def Read(self):
        if not self.Queue.empty():
            ret = self.Queue.get_nowait()
#            if hasattr(self, "old_settings"):
#                print("Read: ", ret)
            return ret

class OutputStream(CommonStream):

    def DirectWrite(self, Data):
        return self.Stream.write(Data)

    def Daemon(self):
        while 1:
            data = self.Queue.get()
            ret = self.DirectWrite(data)
            if not ret:
                if self.Interval == 0:
                    break
                else:
                    time.sleep(self.WriteInterval)
                    continue
            self.SendEvent()

    def Write(self, Data):
        self.WriteQueue.put_nowait(data)

class TextInputStream(InputStream):
    def DirectRead(self):
        return self.Stream.readline()

class InputTerminal(InputStream):
    Buffered = True
    UseBlessed = False

    def __init__(self, Terminal = None, EventQueue = None, Event = True, *args, **kargs):
        if Terminal == None:
            Terminal = blessed.Terminal(*args, **kargs)

        self.CBreakContext = Terminal.cbreak()
        self.Terminal = Terminal
        super().__init__(sys.stdin, EventQueue, Event)

    def DisableBuffering(self):
        self.CBreakContext.__enter__()
        self.Buffered = False

    def RestoreBuffering(self):
        self.CBreakContext.__exit__(None, None, None)

    def BlessedRead(self):
        if self.Buffered:
            return self.Stream.read()
        return self.Terminal.inkey()

    def OwnRead(self):
        Data = ""
        C = self.Stream.read(1)
        Data = C
        while 1:
            self.DisableBlocking()
            C = self.Stream.read(1)
            self.EnableBlocking()
            if len(C) > 0:
                #print("Add char: ", C)
                Data += C
            else:
                #print("End sequence, return data.")
                break
#        print(f"Red: {Data}")
        return Data

    def DirectRead(self):
        if self.UseBlessed:
            return self.BlessedRead()
        return self.OwnRead()
