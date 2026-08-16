
import io
import os
import sys
import fcntl
import termios
import threading
import queue
import time
import blessed

class CommonStream:
    Interval = 0.0
    QueueSizeThreshold = 0

    def __init__(self, Stream = None, EventQueue = None, Event = True, Binary = False, Lines = False, Interval = 0):
        self.Queue = queue.SimpleQueue()
        self.Stream = Stream
        self.Binary = Binary
        self.Lines = Lines
#        print("Got event queue with value: ", EventQueue)
        self.EventQueue = EventQueue
        self.Event = Event
        self.Interval = Interval
        self.ResetState()

    def ResetState(self):
        self.Stop = False
        self.AutoClose = False
        self.Paused = False
        self._IsPaused = False
        while not self.Queue.empty():
            self.Queue.get_nowait()
        while not self.EventQueue.empty():
            self.EventQueue.get_nowait()

    def IsOpen(self):
        return isinstance(self.Stream, io.IOBase) and not self.Stream.closed

    def IsClosed(self):
        return isinstance(self.Stream, io.IOBase) and self.Stream.closed

    def IsStream(self):
        return isinstance(self.Stream, io.IOBase)

    def Open(self):
        if type(self.Stream) == str:
#            print("Opening stream for write: ", self.Stream, self.Mode)
            Mode = self.Mode
            if self.Binary:
                Mode += "b"
            self.Stream = open(self.Stream, self.Mode)
#            print("Stream opened.")
#            print(issubclass(io.IOBase, type(self.Stream)))
            self.SendEvent()

    def Close(self, Timeout = None):
        self.AutoClose = True
        self.Stop = True
        self.Thread.join(Timeout)

    def Pause(self):
        self.Paused = True

    def Resume(self):
        self.Paused = False

    def IsPaused(self):
        return self._IsPaused

    def WaitForPaused(self):
        while not self._IsPaused:
            #print("Waiting...")
            if self.Interval > 0:
                time.sleep(self.Interval)

    def Daemon(self):
        self.Open()

        while not self.Stop:
            if self.Paused:
                self._IsPaused = True
                if self.Interval > 0:
                    time.sleep(self.Interval)
                continue
            else:
                self._IsPaused = False
            ret = self.MainLoop()
            if ret == 0:
                if self.Interval > 0:
                    time.sleep(self.Interval)
                else:
                    #print("Zero data, exiting.")
                    break
        if self.AutoClose:
            self.Stream.close()

    def Activate(self, Stream = None):
        if self.IsActive():
            return 1
        self.ResetState()
        if Stream != None:
            self.Stream = Stream
        self.Thread = threading.Thread(target=self.Daemon, daemon = True)
        self.Thread.start()
        return 0

    def Deactivate(self, Timeout = None):
        self.Stop = True
        self.Thread.join(Timeout)

    def IsActive(self):
        return hasattr(self, "Thread") and self.Thread.is_alive()

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
    Mode = "r"

    def DirectRead(self):
        if self.Lines:
            return self.Stream.readline()
        return self.Stream.read()

    def MainLoop(self):
#        print("Self given:", self)
#        print("An extra argument given:", extra)
#        print(f"Deamon started. Activity status: {self.IsActive()}")

        data = self.DirectRead()
        if len(data) == 0:
            return 0
#            print("Got data:", data)
#            print("Put data to queue.")
#            print("Got data: ", data)
        self.Queue.put_nowait(data)
        self.SendEvent()
        return 1

    def Read(self):
        if not self.Queue.empty():
            ret = self.Queue.get_nowait()
#            if hasattr(self, "old_settings"):
#                print("Read: ", ret)
            return ret

class OutputStream(CommonStream):
    Mode = "w"
    Flush = False

    def DirectWrite(self, Data):
        #print(f"Writing data: \"{Data}\" ({len(Data)})")
        if self.Lines:
            self.Stream.writelines(Data)
            ret = 1
        else:
            ret = self.Stream.write(Data)
        if self.Flush:
            self.Stream.flush()
        return ret

    def Close(self, Timeout = None):
        self.AutoClose = True
        self.Stop = True
        self.Queue.put(None)
        self.Thread.join(Timeout)

    def MainLoop(self):
#        print("Ready to listen for data.")
        data = self.Queue.get()
        if data == None:
            return 0
#        print(f"Got data for write: '{data}'")
        ret = self.DirectWrite(data)
        #print(f"Wrote {ret} of data.")
        if not ret:
            return 0
        self.SendEvent()
        return 1

    def Write(self, Data):
#        print("Put data into queue: ", Data)
#        print("Size of queue: ", self.Queue.qsize())
        self.Queue.put_nowait(Data)
#        print("Size of queue: ", self.Queue.qsize())


class AppendStream(OutputStream):
    Mode = "a"

class InputTerminal(InputStream):
    Buffered = True
    UseBlessed = False

    def __init__(self, Terminal = None, EventQueue = None, Event = True, Interval = 0, UseBlessed = False, *args, **kargs):
        if Terminal == None:
            os.environ["ANSICON"] = "True" # prevent hanging waiting for terminal answer (keypress needed)
            Terminal = blessed.Terminal(*args, **kargs)

        self.CBreakContext = Terminal.cbreak()
        self.Terminal = Terminal
        self.UseBlessed = UseBlessed
        super().__init__(sys.stdin, EventQueue, Event, Interval = Interval)

    def BufferingDisabled(self):
        return self.CBreakContext

    def DisableBuffering(self):
        self.CBreakContext.__enter__()
        self.Buffered = False

    def RestoreBuffering(self):
        self.CBreakContext.__exit__(None, None, None)

    def BlessedRead(self):
        #print(f"Inkey (timeout={self.Interval})")
        return self.Terminal.inkey(timeout=self.Interval)

    def OwnRead(self):
        Data = ""
        C = self.Stream.read(1)
        Data = C
        while 1:
            self.DisableBlocking()
            C = self.Stream.read(1)
            self.EnableBlocking()
            if len(C) > 0:
#                print("Add char: ", C)
                Data += C
            else:
#                print("End sequence, return data.")
                break
#        print(f"Red: {Data}")
        return Data

    def DirectRead(self):
        #print("DirectRead.")
        if self.UseBlessed:
            #print("UseBlessed.")
            return self.BlessedRead()
        #print("Don't UseBlessed.")
        return self.OwnRead()

    def EmulateKey(self, key):
        for c in key:
            # TIOCSTI (Terminal Input Character Simulation) przekazuje bajt do bufora stdin
            fcntl.ioctl(sys.stdin.fileno(), termios.TIOCSTI, c.encode())
