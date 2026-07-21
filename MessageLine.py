
import time
import FitLine

class MessageLine:
    Persistent = None
    Temporary = None
    LineLen = 0
    Timeout = 0
    CurrentTimeout = 0
    StartTime = 0
    FillWith = " "

    def __init__(self, Timeout = None, Msg = None, FillWith = None, LineLen = None):
        if Timeout != None:
            self.Timeout = Timeout
        if Msg != None:
            self.Set(Msg, Timeout)
        if FillWith != None:
            self.FillWith = FillWith
        if LineLen != None:
            self.LineLen = LineLen

    def GetTimeout(self, Timeout = None):
        if Timeout == None:
            Timeout = self.Timeout
            if Timeout == None:
                Timeout = self.__class__.Timeout
        return Timeout

    def GetFillWith(self, FillWith = None):
        if FillWith == None:
            FillWith = self.FillWith
            if FillWith == None:
                FillWith = self.__class__.FillWith
        return FillWith

    def GetLineLen(self, LineLen = None):
        if LineLen == None:
            LineLen = self.LineLen
            if LineLen == None:
                LineLen = self.__class__.LineLen
        return LineLen

    def SetPersistent(self, Msg = None):
        self.Persistent = Msg

    def SetTemporary(self, Msg = None, Timeout = None):
        self.Temporary = Msg
        self.CurrentTimeout = self.GetTimeout(Timeout)
        self.StartTime = time.time()

    def Set(self, Msg, Timeout = None):
        Timeout = self.GetTimeout(Timeout)

        if Timeout > 0:
            self.SetTemporary(Msg, Timeout)
        else:
            self.SetPersistent(Msg)

    def GetMsg(self, Msg = None):
        if Msg != None:
            return Msg
        if self.Temporary == None:
            return self.Persistent
        #print("Check for Temporary")
        ct = time.time()
        to = self.GetTimeout()
        if ct - self.StartTime > to:
            return self.Persistent
        #print("Return persistent")
        return self.Temporary

    def GetLine(self, Msg = None, LineLen = None, FillWith = None):
        Msg = self.GetMsg(Msg)
        if Msg == None or len(Msg) == 0:
            fmt = ""
        else:
            fmt = f"| {Msg} |"
        LineLen =self.GetLineLen(LineLen)
        FillWith = self.GetFillWith(FillWith)
        return FitLine.FitCenter(fmt, LineLen, FillWith)
