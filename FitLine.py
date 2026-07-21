
def ExtendLine(line, minl, char = " "):
    l = len(line)
    if l < minl:
        line = line + char * (minl - l)
    return line

def CutLine(line, maxl):
    l = len(line)
    if l > maxl:
        line = line[:maxl]
    return line

def FitLine(line, Min = None, Max = None, char = " "):
    if Min != None:
        line = CutLine(line, Min)
    if Max != None:
        line = ExtendLine(line, Max, char)
    return line

""" # We dont longer need this stuff

class ClearedLine:
    Len = 0
    PreviousLen = 0
    MaxLen = 0
    MinLen = 0
    def __init__(self, Text = "", MaxLen = None, MinLen = None):
        self.Set(Text)
        if MaxLen != None:
            self.MaxLen = MaxLen
        if MinLen != None:
            self.MinLen = MaxLen

    def GetMaxLen(self, MaxLen = None):
        if MaxLen == None:
            MaxLen = self.MaxLen
            if MaxLen == None:
                MaxLen = self.__class__.MaxLen
        return MaxLen

    def GetMinLen(self, MinLen = None):
        if MinLen == None:
            MinLen = self.MinLen
            if MinLen == None:
                MinLen = self.__class__.MinLen
        return MinLen

    def Set(self, Text, MaxLen = None, MinLen = None):
        Text = Text.rstrip()
        Len = len(Text)
        self.PreviousLen = self.Len
        self.Text = Text
        self.Len = Len

        if MaxLen != None:
            self.MaxLen = MaxLen
        if MinLen != None:
            self.MinLen = MaxLen

    def Append(self, Text):
        Text = Text.rstrip()
        Len = len(Text)
        self.Extra -= Len
        if self.Extra < 0:
            self.Extra = 0
        self.Text += Text
        self.Len = len(self.Text)

    def Get(self, MaxLen = None, MinLen = None):
        MaxLen = self.GetMaxLen(MaxLen)
        MinLen = self.GetMinLen(MinLen)
        Text = self.Text
        Len = self.Len
        if MaxLen > 0 and Len > MaxLen:
            return Text[:MaxLen]
        MinLen = max(MinLen, self.PreviousLen)
        return ExtendLine(Text, MinLen, " ")


    def __str__(self):
        return self.Get()
"""
