
import enum
from blessed import Terminal
from .FormattedValue import FormattedNumber, FormattedTime, SizeStr
from .Message import Message

class UI:
    class Section(enum.Enum):
        WAIT = 0
        HEADER = 1
        MAIN = 2
        FOOTER = 3

    NonDestructive = False
    MinLen = 0
    MaxLen = 0
    Avg = False
    CurrentSection = Section.WAIT

    SimStatusHeight = 15
    AccStatsHeight = 11
    MessageLineHeight = 3

    def __init__(self, SimStatus, AccStats, StorageStats, SystemStats):
        self.FmtNmb = FormattedNumber()
        self.FmtTime = FormattedTime()
        self.FmtNmb.ForbidNegative = True
        self.Terminal = Terminal()
        print(self.Terminal.clear_bol)
        self.First = True
        self.SimStatus = SimStatus
        self.AccStats = AccStats
        self.StorageStats = StorageStats
        self.SystemStats = SystemStats
        self.Msg = Message(Timeout = 2)

    def CacheMaxLen(self, MaxLen = None):
        if MaxLen == None:
            self.MaxLen = self.Terminal.width
        else:
            self.MaxLen = MaxLen

    def GetLen(self, Min = None, Max = None):
        if Min == None:
            Min = self.MinLen
        if Max == None:
            Max = self.MaxLen
        return min(Min, Max), Max

    def PrintLine(self, Text = "", End = "\n", Times = 1):
        while Times:
            print(Text + self.Terminal.clear_eol, end = End)
            Times -= 1

    def PrintStaticLine(self, Text):
        Begin = "\r"
        End = ''
        if self.NonDestructive:
            Begin = ""
            End = "\n"
        self.PrintLine(Begin + Text, End = End)

    def Separator(self):
        minl, maxl = self.GetLen()
        if minl > 1:
            return "+" + "-" * (minl - 2) + "+"
        return ""

    def PrintSeparator(self):
        self.PrintLine(self.Separator())

    def Padding(self):
        minl, maxl = self.GetLen()
        if minl > 1:
            return "|" + " " * (minl - 2) + "|"
        return ""

    def PrintPadding(self):
        self.PrintLine(self.Padding())

    def PrintLeftPadding(self, Text = ""):
        self.PrintLine("|   " + Text)

    def Centered(self, Text):
        lmin, maxl = self.GetLen()
        fmt = f"|{{:^{lmin - 2}}}|"
        fmt = fmt.format(Text)
        return fmt

    def PrintCentered(self, Text):
        self.PrintLine(self.Centered(Text))

    def GetSimSpeeds(self):
        if self.Avg:
            return self.SimStatus.AvgStepSpeed, self.SimStatus.AvgTimeSpeed
        return self.SimStatus.StepSpeed, self.SimStatus.TimeSpeed

    def GetEstSteps(self):
        ems = -1
        if self.Avg:
            ems = self.SimStatus.AvgEstMaxStep
        else:
            ems = self.SimStatus.EstMaxStep
        els = ems - self.SimStatus.Step
        return ems, els

    def GetEstTime(self):
        emt = -1
        if self.Avg:
            emt = self.SimStatus.AvgEstMaxTime
        else:
            emt = self.SimStatus.EstMaxTime
        elt = emt - self.SimStatus.Time
        return emt, elt

    def GetSimETAs(self):
        if self.Avg:
            return self.SimStatus.AvgStepETA, self.SimStatus.AvgTimeETA
        return self.SimStatus.StepETA, self.SimStatus.TimeETA

    def GetDataSpeeds(self):
        if self.Avg:
            return self.AccStats.AvgDataSpeedStep, self.AccStats.AvgDataSpeed
        return self.AccStats.DataSpeedStep, self.AccStats.DataSpeed

    def GetDataESAs(self):
        if self.Avg:
            return self.AccStats.AvgStepESA, self.AccStats.AvgTimeESA
        return self.AccStats.StepESA, self.AccStats.TimeESA

    def GetCPU(self):
        if self.Avg:
            return self.AccStats.AvgCPU
        return self.AccStats.CPU

    def GetStorageESA(self):
        if self.Avg:
            return self.StorageStats.AvgESA
        return self.StorageStats.ESA

    def Message(self, Msg, Timeout = None):
        self.Msg.SetTemporary(Msg, Timeout)

    def Status(self, Msg = None):
        self.Msg.SetPersistent(Msg)

    def WriteHeader(self):
        lmin, lmax = self.GetLen()
#        print(lmin, lmax, Length)
        nd = self.NonDestructive
        self.PrintSeparator()
        self.PrintCentered("Time statistics:")
        self.PrintSeparator()
        self.PrintLeftPadding()
        self.PrintLine(Times=self.SimStatusHeight)

    def WriteSimStatus(self):
        s = self.SimStatus # Less to write
        fn = self.FmtNmb
        ft = self.FmtTime
        minl, maxl = self.GetLen()

        MaxSstr = ""
        LeftSstr = ""
        if s.MaxStep > 0:
            MaxSstr = fn.Str(s.MaxStep)
            LeftSstr = fn.Str(s.StepsLeft)
        else:
            EMS, ELS = self.GetEstSteps()
            MaxSstr = "~" + fn.Str(EMS)
            LeftSstr = "~" + fn.Str(ELS)

        if s.MaxTime > 0:
            MaxTstr = ft.Str(s.MaxTime)
            LeftTstr = ft.Str(s.TimeLeft)
        else:
            EMT, ELT = self.GetEstTime()
            MaxTstr = "~" + ft.Str(EMT)
            LeftTstr = "~" + ft.Str(ELT)

        SSSpeed, STSpeed = self.GetSimSpeeds()
        SETA, TETA = self.GetSimETAs()
        s1 = f"Step:  {fn.Str(s.Step):^15} / {MaxSstr:^15} : {LeftSstr:^15} ({fn.Str(s.StepsProgress):>3}%)," +\
        f"x{fn.Str(SSSpeed):>9}, ETA: {ft.Str(SETA):>20}"

        s2 = f"Sim time: {ft.Str(s.Time):^12} / {MaxTstr:^15} : {LeftTstr:^15} ({fn.Str(s.TimeProgress):>3}%)," +\
        f"x{fn.Str(STSpeed):>9}, ETA: {ft.Str(TETA):>20}"

        s3 = f"Elapsed: {ft.Str(s.ElapsedRealTime):^13}, delta: {ft.Str(s.RealTimeDelta):>10} (Sim: {ft.Str(STSpeed * s.RealTimeDelta):>10}, {ft.Str(s.TimeDelta):>10}/st)"

#        if not self.NonDestructive:
#            print('\r\033[A\033[A\033[A\033[A\033[A', end='')
        self.PrintLeftPadding(s1)
        self.PrintLeftPadding(s2)
        self.PrintLeftPadding(s3)
        self.PrintLeftPadding()
        s.StatsUpdated = False

    def WriteAccStats(self):
        s = self.AccStats
        minl, maxl = self.GetLen()
        SpeedStep, Speed = self.GetDataSpeeds()
        StepESA,TimeESA = self.GetDataESAs()
        self.PrintSeparator()
        self.PrintLeftPadding(f"Data: {SizeStr(s.DataSize):>9}, {SizeStr(Speed):>8}/s |{SizeStr(SpeedStep):>8}/st | ESA:{SizeStr(TimeESA):>8}/{SizeStr(StepESA):>8}.")

    def WriteProcStats(self):
        s = self.ProcStats
        self.PrintSeparator()
        self.PrintLeftPadding(f"Procs: {s.ProcNum}: {s.ProcNames} | CPU: {self.GetCPU()*100:>5.1f}%, mem: {SizeStr(s.Memory):>5} ({s.MemoryRatio:>5.2f}%)")

    def WriteStorageStats(self):
        s = self.StorageStats
        #print(S)
        ESA = self.GetStorageESA()
        self.PrintSeparator()
        self.PrintLeftPadding(f"Storage: {SizeStr(s.Size):>9}, {SizeStr(s.Speed):>8}/s, ESA: {SizeStr(ESA):>8}")

    def WriteSystemStats(self):
        s = self.SystemStats
        self.PrintSeparator()
        self.PrintLeftPadding(f"Avail. res:   mem: {SizeStr(s.FreeMemory):>9}, storage: {SizeStr(s.FreeStorage):>9}")

    def WriteMessageLine(self):
        minl, maxl = self.GetLen()
        self.PrintSeparator()
        self.PrintCentered(self.Msg.GetMsg())
        self.PrintSeparator()

    def WriteSummary(self, Elapsed):
        self.PrintLine()
        self.PrintSeparator()
        self.PrintPadding()
        self.PrintCentered(f"Finishing in {self.FmtTime.Str(Elapsed)}.")
        self.PrintPadding()
        self.PrintSeparator()
        self.PrintLine()

    def Update(self, Force = False):
        self.CacheMaxLen()
        if self.CurrentSection != self.Section.MAIN:
            return
        with self.Terminal.no_line_wrap():
            MoveUp = 0
            if self.First:
                self.WriteHeader()
            if self.SimStatus.StatsUpdated or Force or self.First:
                MoveUp = self.SimStatusHeight
            else:
                MoveUp = self.AccStatsHeight
#            print(f"MoveUp: {MoveUp}")
            if MoveUp and not self.NonDestructive:
                print(self.Terminal.move_up(MoveUp + 1))
            if self.SimStatus.StatsUpdated or Force or self.First:
                self.WriteSimStatus()
            self.WriteAccStats()
            self.WriteProcStats()
            #print(self.StorageStats.Speed)
            self.WriteStorageStats()
            self.WriteSystemStats()
            self.WriteMessageLine()
            self.First = False
