
import os
import sys
import fcntl
import threading
import queue
import time
import blessed

class CommonStream:
    Interval = 0.0

    def __init__(self, Stream = None):
        self.Queue = queue.Queue()
        self.Stream = Stream

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
        return len(self.ReadQueue)

    def DataSize(self):
        return self.Queue.qsize()

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
#                    print("   Input empty, waiting.")
                    time.sleep(self.Interval)
                    continue
#            print("Put data to queue.")
#            print("Got data: ", data)
            self.Queue.put_nowait(data)

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

    def Write(self, Data):
        self.WriteQueue.put_nowait(data)

class TextInputStream(InputStream):
    def DirectRead(self):
        return self.Stream.readline()

class InputTerminal(InputStream):
    Buffered = True
    UseBlessed = False

    def __init__(self, Terminal = None, *args, **kargs):
        if Terminal == None:
            Terminal = blessed.Terminal(*args, **kargs, force_styling=None)

        self.CBreakContext = Terminal.cbreak()
        self.Terminal = Terminal
        super().__init__(sys.stdin)

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
        return Data

    def DirectRead(self):
        if self.UseBlessed:
            return self.BlessedRead()
        return self.OwnRead()
