
import math

def ExtendRight(line, minl, char = " "):
    l = len(line)
    if l < minl:
        line = line + char * (minl - l)
    return line

def ExtendLeft(line, minl, Char = " "):
    l = len(line)
    if l < minl:
        line = Char * (minl - l) + line
    return line

def CutRight(line, maxl):
    l = len(line)
    if l > maxl:
        line = line[:maxl]
    return line

def CutLeft(line, maxl):
    l = len(line)
    if l > maxl:
        line = line[l-maxl:]
    return line

def FitRight(line, Len, char = " "):
    line = CutLeft(line, Len)
    line = ExtendLeft(line, Len, char)
    return line

def FitLeft(line, Len, Char = " "):
    line = CutRight(line, Len)
    line = ExtendRight(line, Len, Char)
    return line

def CutCenter(line, Min):
    l = len(line)
    if l <= Min:
        return line
    diff = l - Min
    half = math.floor(diff / 2)
#    print("Cut by: ", half)
    line = line[:(l - half)]
#    print("Right cut:", line)
    line = line[half:]
#    print("Left cut:", line)
    if len(line) > Min:
#        print(f"Still more than Min, trimming to {Min}.")
        line = line[:Min]
#        print("Trimmed: ", line)
    return line

def ExtendCenter(line, Max, Char = " "):
    l = len(line)
#    print(f"len({line}) = {l}")
    if l >= Max:
#        print("Arg longer than Max.")
        return line
    Max = Max - l
    half = math.floor(Max / 2)
    line = Char * half + line + Char * half
    if len(line) < Max:
        line += Char
    return line

def FitCenter(line, Len, Char = " "):
    line = CutCenter(line, Len)
    line = ExtendCenter(line, Len, Char)
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
