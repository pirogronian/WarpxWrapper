
import math
import datetime

SecInMinute = 60
SecInHour = 3600
SecInDay = 3600 * 24
SecInYear = 3600 * 24 * 365

class FormattedNumber:
    ForbidNegative = False
    FixedPointRange = [99999, 0.001]
    FixedPointPrecision = 2
    def __init__(self, Value = 0, FixedPointPrecision = None, FixedPointRange = None, ForbidNegative = None):
        self.Value = Value
        if FixedPointPrecision != None:
            self.FixedPointPrecision = FixedPointPrecision
        if FixedPointRange != None:
            self.FixedPointRange = FixedPointRange
        if ForbidNegative != None:
            self.ForbidNegative = ForbidNegative

    def GetFixedPointRange(self, Range = None):
        if Range == None:
            Range = self.FixedPointRange
        R1 = 99999
        R2 = 0.001
        if type(Range) == list:
            R1 = Range[0]
            if len(Range) > 1:
                R2 = Range[1]
            else:
                R2 = R1
        else:
            R1 = Range
            R2 = Range
        return R1, R2

    def Str(self, Value = None, FixedPointPrecision = None, FixedPointRange = None, ForbidNegative = None):
        if Value == None:
            Value = self.Value
        if FixedPointPrecision == None:
            FixedPointPrecision = self.FixedPointPrecision
            if FixedPointPrecision == None:
                FixedPointPrecision = self.__class__.FixedPointPrecision
        if FixedPointRange == None:
            Range = self.FixedPointRange
            if Range == None:
                Range = self.__class__.Range
        if ForbidNegative == None:
            ForbidNegative = self.ForbidNegative
            if ForbidNegative == None:
                ForbidNegative = self.__class__.ForbidNegative
        R1, R2 = self.GetFixedPointRange(FixedPointRange)

        #print(f"Str({Value}, {Precision}, {R1}, {R2})")
        if Value < 0 and ForbidNegative:
            return "-/-"
        Style = ""
        if Value == 0:
            FixedPointPrecision = 1
        Abs = abs(Value)
        if Abs > 0 and (Abs > R1 or Abs < R2):
            Style = "e"
        elif type(Value) == float:
            Style = "f"
        elif type(Value) == int:
            Style = "d"
        if  Style == "f":
            if Abs > R2 and Abs < 1:
                tmp = Abs
                while tmp < 1:
                    tmp *= 10
                    FixedPointPrecision += 1
        if Style == "f" or Style == "e":
            fmt = f"{{:.{FixedPointPrecision}{Style}}}"
            return fmt.format(Value)
#            print("Simple integer")
        fmt = f"{{:{Style}}}"
        return fmt.format(Value)

    def __str__(self):
        return self.Str()

def DivideToInt(Number, Divider):
    ret = Number / Divider
    restsec = Number % Divider
    ret = math.floor(ret) # avoid rounding up
    retsec = ret * Divider
    return ret, retsec, restsec

def TimeToSeconds(Years = 0, Days = 0, Hours = 0, Minutes = 0, Seconds = 0):
    Ret = 0
    Ret += SecInYear * Years
    Ret += SecInDay * Days
    Ret += SecInHour * Hours
    Ret += SecInMinute * Minutes
    Ret += Seconds
    return Ret

def DateTimeStr(Seconds, ISOFormat = False, Precision = 0.02, FixedPointPrecision = 2, FixedPointRange = [9999, 0.001]):
    if Seconds < 0:
        return "-/-"
    ret = ""
    Ys, YsSec, RestSec = DivideToInt(Seconds, SecInYear)
    if Ys > 0:
        pl = ""
        if Ys > 1:
            pl = "s"
        ret += str(FormattedNumber(Value = Ys, FixedPointPrecision = FixedPointPrecision, FixedPointRange = FixedPointRange)) + "yr" + pl
#
    if ISOFormat:
        if len(ret) > 0:
            ret += " "
        ret += str(datetime.timedelta(seconds=RestSec))
        return ret

    if RestSec == 0 or RestSec / Seconds < Precision:
        return ret
    Ds, DsSec, RestSec = DivideToInt(RestSec, SecInDay)
    if Ds > 0:
        if len(ret) > 0:
            ret += " "
        ret += f"{Ds}d"
    if RestSec == 0 or RestSec / Seconds < Precision:
        return ret
    Hs, HsSec, RestSec = DivideToInt(RestSec, SecInHour)
    if Hs > 0:
        if len(ret) > 0:
            ret += " "
        ret += f"{Hs}h"
    if RestSec == 0 or RestSec / Seconds < Precision:
        return ret
    Ms, MsSec, RestSec = DivideToInt(RestSec, SecInMinute)
    if Ms > 0:
        if len(ret) > 0:
            ret += " "
        ret += f"{Ms}m"
    if RestSec == 0 or RestSec / Seconds < Precision:
        return ret
    if len(ret) > 0:
        ret += " "
    if type(RestSec) == int:
        return f"{RestSec}s"
    R = FixedPointRange
    if type(R) == list:
        R = R[1]

    if RestSec < R:
        ret += f"{RestSec:.2e}s"
        return ret
    tmp = RestSec
    prec = 3
    while (tmp < 0):
        tmp *= 10
        prec += 1
    fmt = f"{{:.{prec}}}s"
#    print("fmt: ", fmt, "sec:", RestSec)
    ret += fmt.format(RestSec)
    return ret

class FormattedTime:
    Value = 0
    Precision = 0.01
    FixedPointPrecision = 2
    FixedPointRange = [9999, 0.001]
    ISO = False

    def __init__(self, Seconds = 0, ISO = None, Minutes = 0, Hours = 0, Days = 0, Years = 0,  Precision = None, FixedPointPrecision = None, FixedPointRange = None):
        self.SetValue(Seconds = Seconds, Minutes = Minutes, Hours = Hours, Days = Days, Years = Years)
        self.ISO = ISO
        if FixedPointRange != None:
           self.FixedPointRange = FixedPointRange
        if FixedPointPrecision != None:
            self.FixedPointPrecision = FixedPointPrecision
        if Precision != None:
            self.Precision = Precision

    def SetValue(self, Seconds = 0, Minutes = 0, Hours = 0, Days = 0, Years = 0):
        self.Value = TimeToSeconds(Seconds = Seconds, Minutes = Minutes, Hours = Hours, Days = Days, Years = Years)

    def Str(self, Value = None, ISO = None, Precision = None, FixedPointPrecision = None, FixedPointRange = None):
        if Value == None:
            Value = self.Value
        if ISO == None:
            ISO = self.ISO
            if ISO == None:
                ISO = self.__class__.ISO
        if Precision == None:
            Precision = self.Precision
            if Precision == None:
                Precision = self.__class__.Precision
        if FixedPointPrecision == None:
            FixedPointPrecision = self.FixedPointPrecision
            if FixedPointPrecision == None:
                FixedPointPrecision = self.__class__.FixedPointPrecision
        if FixedPointRange == None:
            FixedPointRange = self.FixedPointRange
            if FixedPointRange == None:
                FixedPointRange = self.__class__.FixedPointRange
        return DateTimeStr(Value, ISOFormat = ISO, Precision = Precision, FixedPointPrecision = FixedPointPrecision, FixedPointRange = FixedPointRange)

    def __str__(self):
        return self.Str()

def SizeStr(num, suffix="B"):
    for unit in ("", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"):
        if abs(num) < 1024.0:
            return f"{num:3.1f}{unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f}Yi{suffix}"

