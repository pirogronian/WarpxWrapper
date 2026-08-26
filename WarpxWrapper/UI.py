
#import math
import enum
from .Various import NaN, NaNN, Div
from blessed import Terminal
from .FormattedValue import FormattedNumber, FormattedTime, SizeStr
from .Message import Message
from .Config import Config

class UI:
    MinLen = 0
    MaxLen = 0

    TotalHeight = 19
    SimStatsHeight = 15
    AccStatsHeight = 11
    MessageLineHeight = 3

    Delta = Config.UI.DeltaClass.Arbitrary

    def __init__(self, SimSeq, SystemStats, Control, Config):
        self.Terminal = Control.Terminal
        self.FmtNmb = FormattedNumber()
        self.FmtTime = FormattedTime()
        self.FmtNmb.ForbidNegative = True
        print(self.Terminal.clear_bol)
        self.SimSeq = SimSeq
        self.SystemStats = SystemStats
        self.ControlInput = Control
        self.Config = Config
        self.Msg = Message(Timeout = 2)

    def ResetState(self):
        self.First = True

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
        if not self.Config.UI.Enabled:
            return
        while Times:
            print(Text + self.Terminal.clear_eol, end = End)
            Times -= 1

    def PrintStaticLine(self, Text):
        Begin = "\r"
        End = ''
        if self.Config.UI.NonDestructivePrint:
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

    def GetSimStats(self):
        if self.Config.UI.Sequence:
            return self.SimSeq
        return self.SimSeq.Current

    def UpdateSimStats(self):
        if self.Config.UI.Sequence:
            self.Sim = self.SimSeq
        else:
            self.Sim = self.SimSeq.Current

        if Config.UI.Delta == Config.UI.DeltaClass.Arbitrary:
            self.Stats = self.Sim.Stats
        elif Config.UI.Delta == Config.UI.DeltaClass.Total:
            self.Stats = self.Sim.AvgStats
        else:
            self.Stats = self.Sim.AutoStats

    def GetDeltaName(self):
        if Config.UI.Delta == Config.UI.DeltaClass.Arbitrary:
            return "arbit."
        if Config.UI.Delta == Config.UI.DeltaClass.Total:
            return "total "
        return " auto "

    def GetSimSpeeds(self):
        return self.Stats.RTSteps.Speed, self.Stats.RTTime.Speed

    def GetEstSteps(self):
        ems = self.Stats.StepsTime.MaxValue
        els = ems - self.Sim.Step
        return ems, els

    def GetEstTime(self):
        emt = self.Stats.TimeSteps.MaxValue
        elt = emt - self.Sim.Time
        return emt, elt

    def GetSimETAs(self):
        return self.Stats.RTSteps.ValueLeft, self.Stats.RTTime.ValueLeft

    def GetDataSpeeds(self):
        return self.Stats.DataStep.Speed, self.Stats.DataRTime.Speed

    def GetDataESAs(self):
        return self.Stats.DataStep.MaxValue, self.Stats.DataRTime.MaxValue

    def GetCPU(self):
        return self.Stats.CPU.Speed

    def GetStorage(self):
        return self.Stats.StorageSize

    def Message(self, Msg, Timeout = None):
        self.Msg.SetTemporary(Msg, Timeout)

    def Status(self, Msg = None):
        self.Msg.SetPersistent(Msg)

    def WriteHeader(self):
        if not self.Config.UI.Enabled:
            return
        lmin, lmax = self.GetLen()
#        print(lmin, lmax, Length)

        SeqStr = "sequence"
        if self.Sim == self.SimSeq.Current:
            SeqStr = "current sim."

        DeltaStr = self.GetDeltaName()

        FmtStr = "normal"
        if self.FmtTime.CurrentFormat == FormattedTime.Format.ISO:
            FmtStr = "ISO"
        elif self.FmtTime.CurrentFormat == FormattedTime.Format.RAW:
            FmtStr = "raw"

        StatusStr = f" {SeqStr:^12} | Delta: {DeltaStr} | Format: {FmtStr:^6} "

        self.PrintSeparator()
        self.PrintCentered(StatusStr)
        self.PrintSeparator()
        self.PrintLeftPadding()
        #self.PrintLine(Times=self.SimStatsHeight)

    def WriteSimStats(self):
        if not self.Config.UI.Enabled:
            return
        s = self.Sim # Less to write
        st = self.Stats
        fn = self.FmtNmb
        ft = self.FmtTime
        minl, maxl = self.GetLen()

        MaxSstr = ""
        LeftSstr = ""
        if not NaNN(s.MaxStep):
            MaxSstr = fn.Str(s.MaxStep)
            LeftSstr = fn.Str(s.MaxStep - s.Step)
        else:
            EMS, ELS = self.GetEstSteps()
            MaxSstr = "~" + fn.Str(EMS)
            LeftSstr = "~" + fn.Str(ELS)

        if not NaNN(Config.MaxTime):
            MaxTstr = ft.Str(s.MaxTime)
            LeftTstr = ft.Str(s.MaxTime - s.Time)
        else:
            EMT, ELT = self.GetEstTime()
            MaxTstr = "~" + ft.Str(EMT)
            LeftTstr = "~" + ft.Str(ELT)

        Sp = s.Step / s.MaxStep
        Tp = s.Time / s.MaxTime
        SProgPerc = Sp if NaNN(Sp) else int(Sp * 100)
        TProgPerc = Tp if NaNN(Tp) else int(Tp * 100)

        TermProgress = SProgPerc
        if NaNN(TermProgress):
            TermProgress = TProgPerc
        else:
            if TProgPerc > 0 and TProgPerc < TermProgress:
                TermProgress = TProgPerc
        if not NaNN(TermProgress):
            TermProgress = max(TermProgress, 0)
            TermProgress = min(TermProgress, 100)
            #print("Terminal progress:", TermProgress)
            self.Terminal.progress_bar("normal", TermProgress)

        SSSpeed, STSpeed = self.GetSimSpeeds()
        SSSpeed = Div(1, SSSpeed)
        STSpeed = Div(1, STSpeed)

        SETA, TETA = self.GetSimETAs()

        if self.Config.UI.ProgressBar:
            pbcs = self.Terminal.reverse  #self.Config.PBColors

        s1 = f"Step:  {fn.Str(s.Step):^15} / {MaxSstr:^15} : {LeftSstr:^15} ({fn.Str(SProgPerc):>3}%)," +\
        f"x{fn.Str(SSSpeed):>9}, ETA: {ft.Str(SETA):>20}"

        if self.Config.UI.ProgressBar and Sp >= 0:
            sl = len(s1)
            pbe = int(Sp * sl)
            s1 = pbcs + s1[:pbe] + self.Terminal.normal + s1[pbe:]

        s2 = f"Sim time: {ft.Str(s.Time):^12} / {MaxTstr:^15} : {LeftTstr:^15} ({fn.Str(TProgPerc):>3}%)," +\
        f"x{fn.Str(STSpeed):>9}, ETA: {ft.Str(TETA):>20}"

        if self.Config.UI.ProgressBar and Tp >= 0:
            sl = len(s2)
            pbe = int(Tp * sl)
            s2 = pbcs + s2[:pbe] + self.Terminal.normal + s2[pbe:]

        s3 = f"Elapsed: {ft.Str(s.ElapsedRealTime):^13}, delta: {ft.Str(st.RTSteps.ValueDelta):>10} (Sim: {ft.Str(STSpeed * st.RTSteps.ValueDelta):>10}, {ft.Str(st.RTTime.DomainDelta):>10}/st)"

#        if not self.Config.NonDestructivePrint:
#            print('\r\033[A\033[A\033[A\033[A\033[A', end='')
        self.PrintLeftPadding(s1)
        self.PrintLeftPadding(s2)
        self.PrintLeftPadding(s3)
        self.PrintLeftPadding()

    def WriteAccStats(self):
        if not self.Config.UI.Enabled:
            return
        s = self.Stats

        minl, maxl = self.GetLen()
        SpeedStep, Speed = self.GetDataSpeeds()
        StepESA,TimeESA = self.GetDataESAs()
        self.PrintSeparator()
        self.PrintLeftPadding(f"Data: {SizeStr(s.DataRTime.Value):>9}, {SizeStr(Speed):>8}/s |{SizeStr(SpeedStep):>8}/st | ESA:{SizeStr(TimeESA):>8}/{SizeStr(StepESA):>8}.")

    def WriteProcStats(self):
        if not self.Config.UI.Enabled:
            return
        s = self.ProcStats
        self.PrintSeparator()
        self.PrintLeftPadding(f"Procs: {s.ProcNum}: {s.ProcNames} | CPU: {self.GetCPU()*100:>5.1f}%, mem: {SizeStr(s.Memory):>5} ({s.MemoryRatio:>5.2f}%)")

    def WriteStorageStats(self):
        if not self.Config.UI.Enabled:
            return
        #print(S)
        s = self.GetStorage()
        self.PrintSeparator()
        self.PrintLeftPadding(f"Storage: {SizeStr(s.Value):>9}, {SizeStr(s.Speed):>8}/s, ESA: {SizeStr(s.MaxValue):>8}")

    def WriteSystemStats(self):
        if not self.Config.UI.Enabled:
            return
        s = self.SystemStats
        self.PrintSeparator()
        self.PrintLeftPadding(f"Avail. res:   mem: {SizeStr(s.FreeMemory):>9}, storage: {SizeStr(s.FreeStorage):>9}")

    def WriteMessageLine(self):
        if not self.Config.UI.Enabled:
            return
        minl, maxl = self.GetLen()
        self.PrintSeparator()
        self.PrintCentered(self.Msg.GetMsg())
        self.PrintSeparator()

    def WriteSummary(self, Elapsed):
        if not self.Config.UI.Enabled:
            return
        self.PrintLine()
        self.PrintSeparator()
        self.PrintPadding()
        self.PrintCentered(f"Finishing in {self.FmtTime.Str(Elapsed)}.")
        self.PrintPadding()
        self.PrintSeparator()
        self.PrintLine()

    def Setup(self):
        self.Terminal.set_window_title("WarpxWrapper")

    def Finish(self):
        self.Terminal.set_window_title("")
        self.Terminal.progress_bar('clear')

    def Update(self, Force = False):
        self.CacheMaxLen()
        if not self.Config.UI.Enabled:
            return

        self.UpdateSimStats()

        with self.Terminal.no_line_wrap():
            MoveUp = 0
            if not self.First:
                MoveUp = self.TotalHeight
#            print(f"MoveUp: {MoveUp}")
            if MoveUp and not self.Config.UI.NonDestructivePrint:
                print(self.Terminal.move_up(MoveUp + 1))
            self.WriteHeader()
            self.WriteSimStats()
            self.WriteAccStats()
            self.WriteProcStats()
            #print(self.StorageStats.Speed)
            self.WriteStorageStats()
            self.WriteSystemStats()
            self.WriteMessageLine()
            self.First = False

    def SwitchDestrictive(self):
        self.Config.UI.NonDestructivePrint = not self.Config.UI.NonDestructivePrint
        if not self.Config.UI.NonDestructivePrint:
            self.First = True

    def SwitchSeq(self):
        self.Config.UI.Sequence = not self.Config.UI.Sequence
        if self.Config.UI.Sequence:
            self.Message("All sequence stats")
        else:
            self.Message("Current iteration stats")

    def SwitchDelta(self):
        if Config.UI.Delta == Config.UI.DeltaClass.Arbitrary:
            Config.UI.Delta = Config.UI.DeltaClass.Total
        elif Config.UI.Delta == Config.UI.DeltaClass.Total:
            Config.UI.Delta = Config.UI.DeltaClass.Auto
        else:
            Config.UI.Delta = Config.UI.DeltaClass.Arbitrary

        name = self.GetDeltaName()
        self.Message(f"Delta: {name}")

    def SwitchFormat(self):
        msg = "Format: "
        if self.FmtTime.CurrentFormat == FormattedTime.Format.NORMAL:
            self.FmtTime.CurrentFormat = FormattedTime.Format.ISO
            msg += "ISO"
        elif self.FmtTime.CurrentFormat == FormattedTime.Format.ISO:
            self.FmtTime.CurrentFormat = FormattedTime.Format.RAW
            msg += "Raw"
        elif self.FmtTime.CurrentFormat == FormattedTime.Format.RAW:
            self.FmtTime.CurrentFormat = FormattedTime.Format.NORMAL
            msg += "Normal"
        self.Message(msg)

    def MsgCurrentUpdateInterval(self):
        self.Message(f"Update interval: {self.FmtTime.Str(self.Config.UpdateInterval)}")
