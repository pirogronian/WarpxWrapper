
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

    SimStatusHeight = 15
    AccStatsHeight = 11
    MessageLineHeight = 3

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

    def GetSimStatus(self):
        if self.Config.UI.Sequence:
            return self.SimSeq
        return self.SimSeq.Current

    def UpdateSimStatus(self):
        if self.Config.UI.Sequence:
            self.SimStatus = self.SimSeq
        else:
            self.SimStatus = self.SimSeq.Current

    def GetSimSpeeds(self):
        if self.Config.UI.Average:
            return self.SimStatus.AvgRTSteps.Speed, self.SimStatus.AvgRTTime.Speed
        return self.SimStatus.RTSteps.Speed, self.SimStatus.RTTime.Speed

    def GetEstSteps(self):
        ems = NaN
        if self.Config.UI.Average:
            ems = self.SimStatus.AvgStepsTime.MaxValue
        else:
            ems = self.SimStatus.StepsTime.MaxValue
        els = ems - Config.State.Step
        return ems, els

    def GetEstTime(self):
        emt = NaN
        if self.Config.UI.Average:
            emt = self.SimStatus.AvgTimeSteps.MaxValue
        else:
            emt = self.SimStatus.TimeSteps.MaxValue
        elt = emt - Config.State.Time
        return emt, elt

    def GetSimETAs(self):
        if self.Config.UI.Average:
            return self.SimStatus.AvgRTSteps.ValueLeft, self.SimStatus.AvgRTTime.ValueLeft
        return self.SimStatus.RTSteps.ValueLeft, self.SimStatus.RTTime.ValueLeft

    def GetDataSpeeds(self):
        if self.Config.UI.Average:
            return self.SimStatus.AccStats.AvgDataStep.Speed, self.SimStatus.AccStats.AvgDataRTime.Speed
        return self.SimStatus.AccStats.DataStep.Speed, self.SimStatus.AccStats.DataRTime.Speed

    def GetDataESAs(self):
        if self.Config.UI.Average:
            return self.SimStatus.AccStats.AvgDataStep.MaxValue, self.SimStatus.AccStats.AvgDataRTime.MaxValue
        return self.SimStatus.AccStats.DataStep.MaxValue, self.SimStatus.AccStats.DataRTime.MaxValue

    def GetCPU(self):
        if self.Config.UI.Average:
            return self.SimStatus.AccStats.AvgCPU
        return self.SimStatus.AccStats.CPU

    def GetStorageESA(self):
        if self.Config.UI.Average:
            return self.SimStatus.StorageStats.AvgESA
        return self.SimStatus.StorageStats.ESA

    def Message(self, Msg, Timeout = None):
        self.Msg.SetTemporary(Msg, Timeout)

    def Status(self, Msg = None):
        self.Msg.SetPersistent(Msg)

    def WriteHeader(self):
        if not self.Config.UI.Enabled:
            return
        lmin, lmax = self.GetLen()
#        print(lmin, lmax, Length)
        nd = self.Config.UI.NonDestructivePrint
        self.PrintSeparator()
        self.PrintCentered("Time statistics:")
        self.PrintSeparator()
        self.PrintLeftPadding()
        self.PrintLine(Times=self.SimStatusHeight)

    def WriteSimStatus(self):
        if not self.Config.UI.Enabled:
            return
        s = self.SimStatus # Less to write
        fn = self.FmtNmb
        ft = self.FmtTime
        minl, maxl = self.GetLen()

        MaxSstr = ""
        LeftSstr = ""
        if not NaNN(Config.MaxStep):
            MaxSstr = fn.Str(Config.MaxStep)
            LeftSstr = fn.Str(s.RTSteps.DomainLeft)
        else:
            EMS, ELS = self.GetEstSteps()
            MaxSstr = "~" + fn.Str(EMS)
            LeftSstr = "~" + fn.Str(ELS)

        if not NaNN(Config.MaxTime):
            MaxTstr = ft.Str(Config.MaxTime)
            LeftTstr = ft.Str(s.RTTime.DomainLeft)
        else:
            EMT, ELT = self.GetEstTime()
            MaxTstr = "~" + ft.Str(EMT)
            LeftTstr = "~" + ft.Str(ELT)

        Sp = s.RTSteps.GetProgress()
        Tp = s.RTTime.GetProgress()
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

        s1 = f"Step:  {fn.Str(Config.State.Step):^15} / {MaxSstr:^15} : {LeftSstr:^15} ({fn.Str(SProgPerc):>3}%)," +\
        f"x{fn.Str(SSSpeed):>9}, ETA: {ft.Str(SETA):>20}"

        if self.Config.UI.ProgressBar and Sp >= 0:
            sl = len(s1)
            pbe = int(Sp * sl)
            s1 = pbcs + s1[:pbe] + self.Terminal.normal + s1[pbe:]

        s2 = f"Sim time: {ft.Str(Config.State.Time):^12} / {MaxTstr:^15} : {LeftTstr:^15} ({fn.Str(TProgPerc):>3}%)," +\
        f"x{fn.Str(STSpeed):>9}, ETA: {ft.Str(TETA):>20}"

        if self.Config.UI.ProgressBar and Tp >= 0:
            sl = len(s2)
            pbe = int(Tp * sl)
            s2 = pbcs + s2[:pbe] + self.Terminal.normal + s2[pbe:]

        s3 = f"Elapsed: {ft.Str(s.ElapsedRealTime):^13}, delta: {ft.Str(s.RTSteps.ValueDelta):>10} (Sim: {ft.Str(STSpeed * s.RTSteps.ValueDelta):>10}, {ft.Str(s.RTTime.DomainDelta):>10}/st)"

#        if not self.Config.NonDestructivePrint:
#            print('\r\033[A\033[A\033[A\033[A\033[A', end='')
        self.PrintLeftPadding(s1)
        self.PrintLeftPadding(s2)
        self.PrintLeftPadding(s3)
        self.PrintLeftPadding()

    def WriteAccStats(self):
        if not self.Config.UI.Enabled:
            return
        s = self.SimStatus.AccStats
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
        s = self.SimStatus.StorageStats
        #print(S)
        ESA = self.GetStorageESA()
        self.PrintSeparator()
        self.PrintLeftPadding(f"Storage: {SizeStr(s.Size):>9}, {SizeStr(s.Speed):>8}/s, ESA: {SizeStr(ESA):>8}")

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

        self.UpdateSimStatus()

        with self.Terminal.no_line_wrap():
            MoveUp = 0
            if self.First:
                self.WriteHeader()

            MoveUp = self.SimStatusHeight
#            print(f"MoveUp: {MoveUp}")
            if MoveUp and not self.Config.UI.NonDestructivePrint:
                print(self.Terminal.move_up(MoveUp + 1))
            self.WriteSimStatus()
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

    def SwitchAvg(self):
        self.Config.UI.Average = not self.Config.UI.Average
        self.Message(f"Avg: {self.Config.UI.Average}")

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
