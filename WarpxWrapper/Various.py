
import math
from blessed.keyboard import resolve_sequence, get_keyboard_sequences, get_keyboard_codes

INF = float("inf")

def NaNN(Num):
    return Num == INF or Num == -INF or math.isnan(Num)

def CompareKeys(c1, c2):
    #print(f"{c1} ({type(c1)}) || {c2} ({type(c2)})")
    if type(c1) == type(c2):
        return c1 == c2
    if type(c1) == str:
        if len(c1) == 1:
            return ord(c1) == c2
        else:
            return False
    if len(c2) == 1:
        return c1 == ord(c2)
    return False

TrueStr = [ "t", "y", "true", "yes", "yep" ]
FalseStr = [ "f", "n", "false", "no", "nope" ]

def StrToBool(value):
#        print("Try conversion to float: ", value)
    value = value.lower()
    if value in TrueStr:
        return True
    if value in FalseStr:
        return False

    value = float(value)
#        print("Success: ", value, type(value))
    if value > 0:
        return True

    return False
#        print("Still successful.")

SizeSuff = [ "k", "m", "g", "t", "p", "e", "z" ]

def StrToInt(value):
    mul = 1
    for s in SizeSuff:
        mul *= 1024
        if value[-1:].lower() == s:
            value = value[:-1]
            value = float(value)
            value *= mul
            return int(value)

    return int(value)


def StrToType(value, t):
    if t == bool:
        return StrToBool(value)
    if t == int:
        return StrToInt(value)
    return t(value)

def TypeDescription(t, NonFatal = False):
    if t == bool:
        return "boolean"
    if t == int:
        return "integer"
    if t == float:
        return "float"
    if t == str:
        return "string"
    if NonFatal:
        return t
    raise TypeError("Unsupported type: {}".format(t))

def IterableToStr2D(Iterable, Padding = 2):
    ret = ""
    for item in Iterable:
        ret += " " * Padding + str(item) + "\n"

    return ret

def CreateKeystroke(Data, Terminal):
    return resolve_sequence(Data, get_keyboard_sequences(Terminal), get_keyboard_codes())

def KeyName(Keystroke):
    name = Keystroke.key_name
    value = Keystroke.key_value
    k = None
    if name == None:
        k = value
    else:
        k = name[4:]
        k = k.replace("_", "+")

    return k

def NormalizeKeyName(Key):
    if len(Key) == 1:
        return Key
    Key = Key.replace(" ", "")
    Key = Key.replace("_", "+")
    Key = Key.upper()

    return Key

""""

def CompareSequences(s1, s2):
#    print(f"Compare {s1} =?= {s2}")
    t1 = type(s1)
    t2 = type(s2)
    #print(t1, t2)
    if (t1 != list) and (t2 == list):
        if len(s2) == 1:
            return CompareChars(s1, s2[0])
    if t1 == list and t2 != list:
        #print(f"len(s1) = {len(s1)}, {s2}")
        if len(s1) == 1:
            return CompareChars(s1[0], s2)
        else:
            return False
    if t1 != list and t2 != list:
        return CompareChars(s1, s2)
    l1 = len(s1)
    l2 = len(s2)
    if l1 != l2:
        return False
    i = 0
    while i < l1:
        if not CompareChars(s1[i], s2[i]):
            return False
        i += 1
    return True
"""
