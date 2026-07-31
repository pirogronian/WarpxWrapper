
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

def StrToType(value, t):
    if t == bool:
        return StrToBool(value)
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
