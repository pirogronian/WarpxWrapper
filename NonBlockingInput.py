
import sys
import select
import tty
import termios
from NonBlockingPipe import NonBlockingPipe

class NonBlockingInput(NonBlockingPipe):
    def __init__(self, Stream = sys.stdin):
        super().__init__(Stream)

    def DisableBlocking(self):
        if self.Input == None:
            return
        self.old_settings = termios.tcgetattr(self.Input)
        tty.setcbreak(self.Input.fileno(), termios.TCSANOW)

    def RestoreBlocking(self):
        if self.Input == None or self.old_settings == None:
            return
        termios.tcsetattr(self.Input, termios.TCSADRAIN, self.old_settings) #termios.TCSADRAIN

    def IsData(self):
        if self.Input == None:
            return
        return select.select([self.Input], [], [], 0) == ([self.Input], [], [])

    def DirectRead(self):
        if self.Input == None:
            return
#        print("Reading char from input...")
        return self.Input.read(1)

    def Flush(self):
        if self.Input == None:
            return
        termios.tcflush(self.Input, termios.TCIOFLUSH)

    def ReadSequence(self):
        Ret = []
        while not self.Empty():
            Ret.append(self.Read())
        return Ret
