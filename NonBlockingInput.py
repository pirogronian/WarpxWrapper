
import sys
import select
import tty
import termios
from NonBlockingPipe import NonBlockingPipe

class NonBlockingInput(NonBlockingPipe):
    def __init__(self, Stream = sys.stdin):
        super().__init__(Stream)

    def DisableBuffering(self):
        if self.Input == None:
            return
        self.old_settings = termios.tcgetattr(self.Input)
        tty.setcbreak(self.Input.fileno(), termios.TCSANOW)

    def RestoreBuffering(self):
        if self.Input == None or self.old_settings == None:
            return
        termios.tcsetattr(self.Input, termios.TCSADRAIN, self.old_settings) #termios.TCSADRAIN

    def HasNewData(self):
        if self.Input == None:
            return
        return select.select([self.Input], [], [], 0) == ([self.Input], [], [])

    def DirectRead(self):
        if self.Input == None:
            return
#        print("Reading char from input...")
        Data = ""
        C = self.Input.read(1)
        Data = C
        while 1:
            self.DisableBlocking()
            C = self.Input.read(1)
            self.EnableBlocking()
            if len(C) > 0:
                #print("Add char: ", C)
                Data += C
            else:
                #print("End sequence, return data.")
                break
        return Data

    def Flush(self):
        if self.Input == None:
            return
        termios.tcflush(self.Input, termios.TCIOFLUSH)

