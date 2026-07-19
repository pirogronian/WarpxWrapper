
import sys
import select
import tty
import termios

class NonBlockingInput:
    IOStream = sys.stdin

    def __init__(self, Stream = None):
        if Stream != None:
            self.IOStream = Stream

    def DisableBlocking(self):
        if self.IOStream == None:
            return
        self.old_settings = termios.tcgetattr(self.IOStream)
        tty.setcbreak(self.IOStream.fileno(), termios.TCSANOW)

    def RestoreBlocking(self):
        if self.IOStream == None or self.old_settings == None:
            return
        termios.tcsetattr(self.IOStream, termios.TCSADRAIN, self.old_settings) #termios.TCSADRAIN

    def IsData(self):
        if self.IOStream == None:
            return
        return select.select([self.IOStream], [], [], 0) == ([self.IOStream], [], [])

    def Read(self, num = 1):
        if self.IOStream == None:
            return
        return self.IOStream.read(num)

    def Flush(self):
        if self.IOStream == None:
            return
        termios.tcflush(self.IOStream, termios.TCIOFLUSH)

    def ReadLastChar(self):
        if self.IOStream == None:
            return
        Char = None
        while self.IsData():
            Char = self.Read()
        return Char
