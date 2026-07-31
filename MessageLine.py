
import time

class Message:
    Temporary = None
    Persistent = None
    Timeout = 0
    CurrentTimeout = 0
    StartTime = 0

    def __init__(self, Timeout = None, Msg = None):
        if Timeout != None:
            self.Timeout = Timeout
        if Msg != None:
            self.Set(Msg, Timeout)

    def GetTimeout(self, Timeout = None):
        if Timeout == None:
            Timeout = self.Timeout
        return Timeout

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

    def GetPersistent(self):
        if self.Persistent == None:
            return ""
        return self.Persistent

    def GetTemporary(self):
        if self.Temporary == None:
            return ""
        return self.Temporary

    def GetMsg(self, Msg = None):
        if Msg != None:
            return Msg
        if self.Temporary == None:
            return self.GetPersistent()
        #print("Check for Temporary")
        ct = time.time()
        to = self.GetTimeout()
        if ct - self.StartTime > to:
            return self.GetPersistent()
        #print("Return persistent")
        return self.GetTemporary()

