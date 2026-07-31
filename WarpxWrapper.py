#!/usr/bin/python -u

import sys
import os
import subprocess
import regex
import time
import datetime
import pathlib
import argparse
import enum
import signal
import shutil
import stat
import pypsutil
from blessed import Terminal
from queue import SimpleQueue

from FormattedValue import FormattedNumber, FormattedTime, SizeStr
from NonBlockingStream import InputStream, InputTerminal, OutputStream
from MessageLine import MessageLine
from Timer import Timer
from Various import CompareKeys
from Logger import Logger, Verbosity
import Processes
from ControlManager import ControlManager
from Storage import DirSize
from ConfigManager import ConfigManager, IncludeAction

class SourceType(enum.Enum):
    DEFAULT = 0 # It means the COMMAND
    COMMAND = 1
    FILE    = 2
    STDIN   = 3

DefaultWarpxInputFileName = "input"

class Config:
    MaxParamLength = 0
    LogLevel = Verbosity.INFO # It does nothig, but must be due to AddParam() requirements
    Quiet = False
    ErrorIsFatal = True
    UpdateInterval = 0.5
    StorageInterval = 5.0
    DontRun = False

    LogFile = "Log.txt"
    StoragePath = "diags"

    MaxStep = -1
    MaxTime = -1.0

    Source = SourceType.DEFAULT

    ExecBase = "warpx."
    ExecDim = "3d"

    Executable = ""
    Command = ""

    UseMpi = False

    InputFile = ""
    IsFifo = True

    PID = 0
    AbortOnExit = False

    SkipMain = False
    SkipFooter = False
    DontWaitForFooter = True
    NonDestructivePrint = False

    BreakKey = "\x1b"
    ISOKey = "f"
    NDestPrintKey = "d"
    PauseKey = ' '

Logger = Logger("WarpxWrapper")

def Error(*args):
    if args:
        Logger.Error(*args)
    if Config.ErrorIsFatal:
        Logger.Error(" ^^^^ An error occured, aborting. ^^^^")
        exit(1)

def Fatal(*args):
    if args:
        Logger.Critical(*args)
        Logger.Critical(" ^^^^ An error occured, aborting. ^^^^")
        exit(1)

def IsReadable(fname):
    return os.access(fname, os.R_OK)

def IsWritable(fname):
    return os.access(fname, os.W_OK)

def setLogLevel(level):
    Logger.Level = level

def getLogLevel():
    return Logger.Level

CM = ConfigManager(
    Config,
    Logger,
    Error = Error,
    Description = "Small script for showing realtime WarpX time and progress stats and (optionally) to help running it.")

CM.ExecEnv = {
        "Verbosity" : Verbosity,
        "SourceType" : SourceType,
        "getLogLevel" : getLogLevel,
        "setLogLevel" : setLogLevel
        }

CM.ExecEnvExcl = [ "LogLevel" ]

def PrintParam(name, MinLength = 0):
    Value = getattr(Config, name)
    Type = type(Value)
    Extra = MinLength - len(name)
    if Extra < 0:
        Extra = 0
    if Type == str:
        Value = f"\"{Value}\""
    fmt = f"{name} = " + Extra * "-" + f" {Value} ({Type.__name__})"
    Logger.Debug(1, fmt)

def PrintParams():
    Logger.Debug("Printing current configuration:")
    for name in CM.Params:
        PrintParam(name, Config.MaxParamLength)

LogLevels = {
        'debug': Verbosity.DEBUG,
        'info': Verbosity.INFO,
        'warning': Verbosity.WARNING,
        'error' : Verbosity.ERROR,
        'critical' : Verbosity.CRITICAL
    }

class VerbosityAction(argparse.Action):
    def __init__(self, option_strings, dest, **kwargs):
        kwargs.pop("VarName")
        super().__init__(option_strings, dest, **kwargs)
    def __call__(self, parser, namespace, value, option_string):
        global Config
        setLogLevel(LogLevels[value])
        Logger.Debug("Command line: set LogLevel to '{}'.".format(value))
#parser.add_argument("-v", "--verbosity", nargs='?', action=VerboseAction, const='debug', choices = LogLevels.keys())

CM.Parser.add_argument("-I", "--include", nargs='+', action=IncludeAction)

Sources = {
        'command': SourceType.COMMAND,
        'file': SourceType.FILE,
        'stdin': SourceType.STDIN
    }

class SourceAction(argparse.Action):
    def __init__(self, option_strings, dest, **kwargs):
        kwargs.pop("VarName")
        super().__init__(option_strings, dest, **kwargs)
    def __call__(self, parser, namespace, value, option_string):
        global Source
        key = value[0]
        Config.Source = Sources[key]
        Logger.Debug("Command line: set Source to {}".format(key))

class CommandAction(argparse.Action):
    def __init__(self, option_strings, dest, **kwargs):
        kwargs.pop("VarName")
        super().__init__(option_strings, dest, **kwargs)
    def __call__(self, parser, namespace, value, option_string):
        Config.Command = value
        Logger.Debug("Command line: set Command to {}".format(value))
#parser.add_argument("-s", "--source", nargs=1, action=SourceAction, choices=Sources.keys())

CM.AddParam("LogLevel", "-v", "--verbosity", action=VerbosityAction, const='debug', choices=LogLevels.keys())
CM.AddParam("Quiet", "-q", "--quiet", const = True)
CM.AddParam("DontRun", "-r", "--dont-run", const = True)
CM.AddParam("ErrorIsFatal", "--error-fatal", const = True)
CM.AddParam("LogFile", "-l", "--log-file")
CM.AddParam("StoragePath", "-o", "--storage")
CM.AddParam("NonDestructivePrint", "-d", "--non-destructive-print", const = True)
CM.AddParam("UpdateInterval", "-u", "--upd-int", "--update-interval")
CM.AddParam("StorageInterval", "--st--int", "--storage-interval")
CM.AddParam("MaxStep", "-x", "--max-steps")
CM.AddParam("MaxTime", "-t", "--max-time")
CM.AddParam("SkipMain", "-a", "--skip-main-loop", const = True)
CM.AddParam("SkipFooter", "-f", "--skip-footer", const = True)
CM.AddParam("DontWaitForFooter", "--dont-wait-for-footer", const = True)
CM.AddParam("Source", "-s", "--source", action=SourceAction, choices=Sources.keys())
CM.AddParam("PID", "-p", "--pid")
CM.AddParam("AbortOnExit", "-k", "--abort-on-exit", const = True)
CM.AddParam("InputFile","-i", "--input-file")
CM.AddParam("IsFifo", "--fifo", "--pipe", const = True)
CM.AddParam("ExecBase", "--exec-base")
CM.AddParam("ExecDim", "--dim", "--exec-dim")
CM.AddParam("Executable", "--executable")
CM.AddParam("UseMpi", "-m", "--use-mpi", const = True)
CM.AddParam("Command", "-c", "--command", nargs="+", action=CommandAction)
CM.Parser.add_argument("command", nargs="*")

DefaultConfigFile = "config.py"
if IsReadable(DefaultConfigFile): # Always try, never cry.
    CM.IncludeFile(DefaultConfigFile)
else:
    Logger.Debug(f"Cannot read default config file: '{DefaultConfigFile}'")

args = CM.Parse(sys.argv[1:])
if len(args.command) > 0:
    Config.Command = args.command

class SimulationStats:
    Step = -1 # These two are replenished externally
    Time = -1

    MaxStep = -1 # These two are set once at the beginning
    EstMaxStep = -1
    AvgEstMaxStep = -1
    MaxTime = -1
    EstMaxTime = -1
    AvgEstMaxTime = -1

    StepsLeft = -1
    EstStepsLeft = -1
    TimeLeft = -1
    EstTimeLeft = -1


    StepsProgress = -1
    TimeProgress = -1

    CurrentRealTime = 0 # This is replenished automatically

    PrevStep = 0
    PrevTime = 0
    PrevRealTime = 0

    StartRealTime = 0
    ElapsedRealTime = 0

    StepDelta = -1
    TimeDelta = -1 # This also is replenished externally
    RealTimeDelta = -1

    StepSpeed = 0
    TimeSpeed = 0

    AvgStepSpeed = 0
    AvgTimeSpeed = 0

    StepETA = -1
    TimeETA = -1

    AvgStepETA = -1
    AvgTimeETA = -1

    TimePerStep = -1
    StepsPerTime = -1
    AvgTimePerStep = -1
    AvgStepsPerTime = -1

    ElapsedInternalRealTime = -1
    InternalRealTimeDelta = -1

    ElapsedRealTimeEfficiency = -1
    RealTimeDeltaEfficiency = -1

    def __init__(self, MaxStep, MaxTime):
        self.MaxStep = MaxStep
        self.MaxTime = MaxTime
#        self.StartRealTime = time.time()
        self.Updated = False

    def CalculateETA(self):
        self.StepDelta = self.Step - self.PrevStep
        # TimeDelta was provided externally, but is no longer
        self.TimeDelta = self.Time - self.PrevTime

        self.RealTimeDelta = self.CurrentRealTime - self.PrevRealTime

        if self.MaxStep > 0 and self.StepDelta > 0:
            self.TimePerStep = self.TimeDelta / self.StepDelta
            self.EstMaxTime = self.Time + self.TimePerStep * self.StepsLeft

            self.AvgTimePerStep = self.Time / self.Step
            self.AvgEstMaxTime = self.Time + self.AvgTimePerStep * self.StepsLeft

        if self.MaxTime > 0 and self.TimeDelta > 0:
            self.StepsPerTime = self.StepDelta / self.TimeDelta
            self.EstMaxStep = self.Step + self.StepsPerTime * self.TimeLeft

            self.AvgStepsPerTime = self.Step / self.Time
            self.AvgEstMaxStep = self.Step + self.AvgStepsPerTime * self.TimeLeft

        if self.RealTimeDelta > 0:
            self.StepSpeed = self.StepDelta / self.RealTimeDelta
            self.TimeSpeed = self.TimeDelta / self.RealTimeDelta
            #print(f"Set StepSpeed: {self.StepSpeed}, ({self.StepDelta} / {self.RealTimeDelta})")
            #print(f"Set TimeSpeed: {self.TimeSpeed}, ({self.TimeDelta} / {self.RealTimeDelta})")

        if self.StepSpeed > 0:
            self.StepETA = self.StepsLeft / self.StepSpeed
        if self.TimeSpeed > 0:
            self.TimeETA = self.TimeLeft / self.TimeSpeed

    def CalculateAvgETA(self):
        self.AvgStepSpeed = self.Step / self.ElapsedRealTime
        if self.AvgStepSpeed > 0:
            self.AvgStepETA = self.StepsLeft / self.AvgStepSpeed

        self.AvgTimeSpeed = self.Time / self.ElapsedRealTime
        if self.AvgTimeSpeed > 0:
            self.AvgTimeETA = self.TimeLeft / self.AvgTimeSpeed

    def Recalculate(self, Time = None):
        if self.Step <= self.PrevStep:
            Logger.Warning(f"Step {self.Step} <= last step: {self.PrevStep}. Nothing to calculate.")
            return
        if Time == None:
            Time = time.time()

        if self.StartRealTime == 0:
            self.StartRealTime = Time

#        print(f"TimeDelta: {self.TimeDelta}, StepDelta: {self.StepDelta}")

        self.CurrentRealTime = Time
        self.ElapsedRealTime = self.CurrentRealTime - self.StartRealTime - self.PausedTime

        if self.Step >= 0 and self.MaxStep > 0:
            self.StepsLeft = self.MaxStep - self.Step

        if self.Time >= 0 and self.MaxTime > 0:
            self.TimeLeft = self.MaxTime - self.Time

        self.StepsProgress = int((self.Step / self.MaxStep) * 100)
        self.TimeProgress = int((self.Time / self.MaxTime) * 100)

        self.CalculateETA()
        if self.ElapsedRealTime > 0:
            self.CalculateAvgETA()

        if self.ElapsedRealTime > 0:
            self.ElapsedRealTimeEfficiency = int((self.ElapsedInternalRealTime /  self.ElapsedRealTime) * 100)
        if self.RealTimeDelta > 0:
            self.RealTimeDeltaEfficiency = int((self.InternalRealTimeDelta / self.RealTimeDelta) * 100)

        self.PrevStep = self.Step
        self.PrevTime = self.Time
        self.PrevRealTime = self.CurrentRealTime
        self.Updated = True

class AccStats:
    UpdNr = 0
    Step = 0
    PrevStep = 0
    DataSize = 0
    PrevDataSize = 0
    PrevStepDataSize = 0

    StartTime = -1
    Elapsed = 0

    CurrentTime = 0
    PrevTime = 0

    DataSpeed = 0
    AvgDataSpeed = 0

    DataSpeedStep = 0
    AvgDataSpeedStep = 0

    StepESA = 0
    TimeESA = 0

    AvgStepESA = 0
    AvgTimeESA = 0

    CPUStart = 0
    CPUTime = 0
    PrevCPUTime = 0
    CPU = 0
    AvgCPU = 0

    def Recalculate(self):
        self.UpdNr += 1
        self.CurrentTime = time.time()
        if self.StartTime < 0:
            self.StartTime = self.CurrentTime
        self.Elapsed = self.CurrentTime - self.StartTime - self.PausedTime
        #print(f"Upd # {self.UpdNr}. Loop: {self.Loop}.")
        #print(f"CTime: {self.CurrentTime:.2f}, prev time: {self.PrevTime:.2f}")

        self.Delta = self.CurrentTime - self.PrevTime
        self.DataDelta = self.DataSize - self.PrevDataSize
        self.CPUDelta = self.CPUTime - self.PrevCPUTime

        if self.Delta > 0:
            self.DataSpeed = self.DataDelta / self.Delta
            self.CPU = self.CPUDelta / self.Delta

        if self.Elapsed > 0:
            self.AvgDataSpeed = self.DataSize / self.Elapsed

        if self.CPUStart > 0:
            self.AvgCPU = self.CPUTime / (time.time() - self.CPUStart - self.PausedTime)
            #print(f"Set AvgCPU: {self.CPUTime} / {time.time()} - {self.CPUStart} = / {time.time() - self.CPUStart} = {self.AvgCPU}")

        self.PrevTime = self.CurrentTime
        self.PrevDataSize = self.DataSize
        self.PrevCPUTime = self.CPUTime
        #print(f"DDelta: {self.DataDelta} / {self.Delta:.2f}, {self.DataSpeed:.2f}/s")

    def RecalculateStep(self):
        if self.Step <= self.PrevStep:
            Logger.Warning(f"Step: {self.Step} <= LastStep: {self.LastStep}. Nothing to calculate.")
            return

        self.StepDelta = self.Step - self.PrevStep
        self.DataStepDelta = self.DataSize - self.PrevStepDataSize
        if self.DataStepDelta > 0:
            self.DataSpeedStep = self.DataStepDelta / self.StepDelta
        if self.Step > 0:
            self.AvgDataSpeedStep = self.DataSize / self.Step
        self.LastStep = self.Step

class StorageStats:
    RawSize = 0
    Size = 0
    StartSize = -1
    StartTime = -1
    PausedTime = 0
    Elapsed = 0
    Speed = 0
    ESA = 0
    AvgESA = 0

    def Recalculate(self):
        if self.StartTime < 0:
            self.StartTime = time.time()
        self.Size = self.RawSize - self.StartSize
        self.Elapsed = time.time() - self.StartTime - self.PausedTime
        if self.Elapsed > 0:
            self.Speed = self.Size / self.Elapsed
            #print(f"St Speed: {self.Speed:.2f}, {SizeStr(self.Size)} - {SizeStr(self.StartSize)} = {SizeStr(self.Size - self.StartSize)} / {self.Elapsed:.4f}")

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

    SimStatsHeight = 11
    AccStatsHeight = 7
    MessageLineHeight = 1

    def __init__(self, SimStats, AccStats, StorageStats):
        self.FmtNmb = FormattedNumber()
        self.FmtTime = FormattedTime()
        self.FmtNmb.ForbidNegative = True
        self.Terminal = Terminal()
        print(self.Terminal.clear_bol)
        self.First = True
        self.SimStats = SimStats
        self.AccStats = AccStats
        self.StorageStats = StorageStats
        self.MsgLine = MessageLine(Timeout = 2, FillWith = "-", LineLen = 77)

    def CacheMaxLen(self, MaxLen = None):
        if MaxLen == None:
            self.MaxLen = shutil.get_terminal_size().columns
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
            return self.SimStats.AvgStepSpeed, self.SimStats.AvgTimeSpeed
        return self.SimStats.StepSpeed, self.SimStats.TimeSpeed

    def GetEstSteps(self):
        ems = -1
        if self.Avg:
            ems = self.SimStats.AvgEstMaxStep
        else:
            ems = self.SimStats.EstMaxStep
        els = ems - self.SimStats.Step
        return ems, els

    def GetEstTime(self):
        emt = -1
        if self.Avg:
            emt = self.SimStats.AvgEstMaxTime
        else:
            emt = self.SimStats.EstMaxTime
        elt = emt - self.SimStats.Time
        return emt, elt

    def GetSimETAs(self):
        if self.Avg:
            return self.SimStats.AvgStepETA, self.SimStats.AvgTimeETA
        return self.SimStats.StepETA, self.SimStats.TimeETA

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

    def WriteHeader(self):
        lmin, lmax = self.GetLen()
#        print(lmin, lmax, Length)
        nd = self.NonDestructive
        self.PrintSeparator()
        self.PrintCentered("Time statistics:")
        self.PrintSeparator()
        self.PrintLeftPadding()
        self.PrintLine(Times=11)

    def WriteSimStats(self):
        s = self.SimStats # Less to write
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

        s3 = f"Elapsed: {ft.Str(s.ElapsedRealTime)}, delta: {ft.Str(s.RealTimeDelta)} ({ft.Str(s.TimeDelta * s.RealTimeDelta)}), eff: elapsed: {s.ElapsedRealTimeEfficiency}%, delta: {s.RealTimeDeltaEfficiency}%"

#        if not self.NonDestructive:
#            print('\r\033[A\033[A\033[A\033[A\033[A', end='')
        self.PrintLeftPadding(s1)
        self.PrintLeftPadding(s2)
        self.PrintLeftPadding(s3)
        self.PrintLeftPadding()
        s.Updated = False

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

    def WriteMessageLine(self):
        minl, maxl = self.GetLen()
        self.PrintLine(f"+{self.MsgLine.GetLine(LineLen = minl - 2)}+")

    def WriteSummary(self, Elapsed):
        self.PrintLine()
        self.PrintSeparator()
        self.PrintPadding()
        self.PrintCentered(f"Finishing in {self.FmtTime.Str(Elapsed)}.")
        self.PrintPadding()
        self.PrintSeparator()
        self.PrintLine()

    def Rewrite(self):
        self.CacheMaxLen()
        if self.CurrentSection != self.Section.MAIN:
            return
        with self.Terminal.no_line_wrap():
            MoveUp = 0
            if self.First:
                self.WriteHeader()
            if self.SimStats.Updated or self.First:
                MoveUp = self.SimStatsHeight
            else:
                MoveUp = self.AccStatsHeight
#            print(f"MoveUp: {MoveUp}")
            if MoveUp and not self.NonDestructive:
                print(self.Terminal.move_up(MoveUp + 1))
            if self.SimStats.Updated or self.First:
                self.WriteSimStats()
            self.WriteAccStats()
            self.WriteProcStats()
            #print(self.StorageStats.Speed)
            self.WriteStorageStats()
            self.WriteMessageLine()
            self.First = False

class State:
    Header = True
    Footer = False
    SkipMain = False

    MainUpdated = False
    SecondUpdated = False
    ThirdUpdated = False

ReHeadStr = "For full input parameters, see the file\\:"
Re1     = regex.compile("TIME")
Re2     = regex.compile("Evolve time")
ReHead  = regex.compile(ReHeadStr)
ReFoot  = regex.compile("Total Time")
ReAbort = regex.compile("MPI_ABORT")
ReNum   = regex.compile("[+-]?(?:[0-9]+(?:\\.[0-9]+)?|\\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
#ReNum = regex.compile("[0-9]+(.[0-9]+(e[+-][0-9]+)?)?")


class WarpxWrapper:
    UpdateInterval = 0.5
    StartTime = -1
    PausedAt = -1
    Pausedtime = 0
    Paused = False
    WarpxProcess = None
    Finishing = False

    def __init__(self):
        self.State = State()
        self.UpdateInterval = Config.UpdateInterval
        self.SimStats = SimulationStats(Config.MaxStep, Config.MaxTime)
        self.AccStats = AccStats()
        self.StorageStats = StorageStats()
        self.UI = UI(self.SimStats, self.AccStats, self.StorageStats)
        self.Control = ControlManager()
        self.EventQueue = SimpleQueue()
        self.DataInput = InputStream(Lines = True, EventQueue = self.EventQueue, Event = 1)
        self.ControlInput = InputTerminal(self.UI.Terminal, EventQueue = self.EventQueue, Event = 2)
        self.UpdateTimer = Timer(Config.UpdateInterval)
        self.StorageTimer = Timer(Config.StorageInterval)
        self.PausedTime = 0

    def RegisterActions(self):
        self.Control.Register(Config.BreakKey, self.UserBreak)
        self.Control.Register(Config.ISOKey, self.SwitchISO)
        self.Control.Register("a", self.SwitchAvgStats)
        self.Control.Register(Config.NDestPrintKey, self.SwitchDestrictive)
        self.Control.Register(Config.PauseKey, self.SwitchRunningState)

    def PrepareStdin(self):
        self.DataInput.Input = sys.stdin
        self.ControlInput.Stream = None

    def PrepareInputFileName(self):
        IsFifo = Config.IsFifo
        Logger.Debug(f"Opening WarpX output file: '{Config.InputFile}'")
        Path = pathlib.Path(Config.InputFile)
        if Path.is_file():
            if Path.is_fifo():
                IsFifo = True
            else:
                IsFifo = False
        elif Path.is_fifo():
            IsFifo = True
        else:
            if IsFifo:
                os.mkfifo(Config.InputFile)
            else:
                os.mknod(Config.InputFile, stat.S_IFREG | 0o600)
        if IsFifo:
            Logger.Debug("Input file is a pipe. Open it inside thread.")
            self.DataInput.Stream = Config.InputFile
        else:
            Logger.Debug("Input fle is an ordinary file. Don't exit if read zero bytes.")
            self.DataInput.Interval = Config.UpdateInterval
            try:
                DataStream = open(Config.InputFile, "r")
            except Exception as e:
                Logger.ExceptCritic(e)
                Fatal(f"Cannot open data file '{Config.InputFile}' for reading.")
            self.DataInput.Stream = DataStream
            Logger.Debug(f"File '{Config.InputFile}' successfully opened.")

    def PrepareCommand(self):
        CmdArgs = []

        if Config.UseMpi:
            CmdArgs.append("mpirun")

        if type(Config.Command) == str and Config.Command != "":
            CmdArgs.extend(Config.Command.split())
        elif type(Config.Command) == list and len(Config.Command) > 0:
            for arg in Config.Command:
                subargs = arg.split()
                CmdArgs.extend(subargs)
        else:
            if Config.Executable != "":
                CmdArgs.append(Config.Executable)
            else:
                CmdArgs.append(Config.ExecBase + Config.ExecDim)

        if Config.Command == "":
            if Config.InputFile == "":
                Config.InputFile = DefaultWarpxInputFileName
            if not IsReadable(Config.InputFile):
                Error(f"Warpx input file \"{Config.InputFile}\" is not readable.")

            CmdArgs.append(Config.InputFile)

        RunMsg = f"|   Running WarpX 3D with the following command: {CmdArgs}   |"
        RunMsgLen = len(RunMsg)

        Panel = "-" * RunMsgLen
        Logger.Debug(Panel)
        Logger.Debug(RunMsg)
        Logger.Debug(Panel)

        try:
            self.WarpxProcess = pypsutil.Popen(args=CmdArgs,
                                        stdin=subprocess.DEVNULL,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT,
                                        text=True)
        except Exception as e:
            Logger.ExceptCrit(e)
            Fatal("Cannot create a subprocess to get its output.")

        self.DataInput.Stream = self.WarpxProcess.stdout

    def PrepareSource(self):
        if Config.Source == SourceType.STDIN:
            self.PrepareStdin()
        elif Config.Source == SourceType.FILE:
            self.PrepareInputFileName()
        else:
            self.PrepareCommand()

    def PrepareLogOutput(self):
        if Config.LogFile == None and Config.LogFile == "":
            return
        Logger.Debug(f"Opening log file: '{Config.LogFile}'")
        Path = pathlib.Path(Config.LogFile)
        if Path.is_file():
            if Path.is_fifo():
                IsFifo = True
            else:
                IsFifo = False
        elif Path.is_fifo():
            IsFifo = True
        else:
            if IsFifo:
                os.mkfifo(Config.InputFile)
            else:
                os.mknod(Config.InputFile, stat.S_IFREG | 0o600)
        self.LogOutput = OutputStream()
        self.LogOutput.Flush = True
        if IsFifo:
            Logger.Debug("Log file is a pipe. Open it inside thread.")
            self.LogOutput.Stream = Config.InputFile
        else:
            Logger.Debug("Log file is an ordinary file.")
            LogStream = None
            try:
                LogStream = open(Config.LogFile, "w")
            except Exception as e:
                Logger.ExceptError(e)
                Error(f"Cannot open log file '{Config.LogFile}' for writing.")
            self.LogOutput.Stream = LogStream
            Logger.Debug(f"File '{Config.LogFile}' successfully opened.")

    def PrepareDataStream(self):
        self.DataInput.QueueSizeThreshold = 100

    def ActivateStreams(self):
        Logger.Debug("Activating non-blocking data input.")
        self.DataInput.Activate()
        Logger.Debug(1, f"Input activity status: {self.DataInput.IsActive()}.")

        if self.ControlInput.Stream != None:
            Logger.Debug("Activating non-blocking control input.")
            self.ControlInput.Activate()
            Logger.Debug(1, f"Input Activity status: {self.ControlInput.IsActive()}.")
        else:
            Logger.Debug("Stdin used for data, don't activate control input.")

        if self.LogOutput != None:
            Logger.Debug("Activating non-blocking log output.")
            self.LogOutput.Activate()
            Logger.Debug(1, f"Output Activity status: {self.LogOutput.IsActive()}.")

    def CloseStreams(self):
        self.DataInput.Close(0)
        #self.ControlInput.Stream.close() # stdin shouldnt be closed, right?
        if self.LogOutput != None:
            self.LogOutput.Close()

    def ParseUsedInput(self, fname):
        try:
            f = open(fname, "r")
        except:
            Logger.Warning(f"Cannot open used input file: '{fname}'")
            return

        line = ""
        ReMaxStep = regex.compile("max_step = ")
        ReStopTime = regex.compile("stop_time = ")
        while 1:
            line = f.readline()
            if line == "":
                break
            if ReMaxStep.search(line):
                nums = ReNum.findall(line)
                try:
                    self.SimStats.MaxStep = int(nums[len(nums) - 1])
                except Exception as e:
                    Logger.ExceptWarn(e)
            if ReStopTime.search(line):
                nums = ReNum.findall(line)
                try:
                    self.SimStats.MaxTime = float(nums[len(nums) - 1])
                except Exception as e:
                    Logger.ExceptWarn(e)

    def OnKey(self, Key):
        if not self.Control.Dispatch(Key):
            self.UI.MsgLine.SetTemporary(f"Key: {Key.encode()}")
        if not self.Finishing:
            self.UI.Rewrite()

    def ProcessControlInput(self):
        while 1:
            Key = self.ControlInput.Read()
            if Key == None:
                break
            self.OnKey(Key)
            if self.Finishing:
                break

    def Pause(self):
        if self.WarpxProcess != None:
            Processes.PauseTree(self.WarpxProcess)
        self.PausedAt = time.time()
        self.Paused = True
        self.UI.MsgLine.SetPersistent("Paused")

    def Resume(self):
        if self.WarpxProcess != None:
            Processes.ResumeTree(self.WarpxProcess)
        self.Pausedtime += time.time() - self.PausedAt
        self.Paused = False
        self.UI.MsgLine.SetPersistent()
        self.UI.MsgLine.SetTemporary("Resumed")

    def SwitchRunningState(self):
        if self.Paused:
            self.Resume()
        else:
            self.Pause()

    def SwitchDestrictive(self):
        self.UI.NonDestructive = not self.UI.NonDestructive

    def SwitchAvgStats(self):
        self.UI.Avg = not WW.UI.Avg
        self.UI.MsgLine.SetTemporary(f"Avg: {WW.UI.Avg}")

    def SwitchISO(self):
        msg = "Format: "
        if self.UI.FmtTime.CurrentFormat == FormattedTime.Format.NORMAL:
            self.UI.FmtTime.CurrentFormat = FormattedTime.Format.ISO
            msg += "ISO"
        elif self.UI.FmtTime.CurrentFormat == FormattedTime.Format.ISO:
            self.UI.FmtTime.CurrentFormat = FormattedTime.Format.RAW
            msg += "Raw"
        elif self.UI.FmtTime.CurrentFormat == FormattedTime.Format.RAW:
            self.UI.FmtTime.CurrentFormat = FormattedTime.Format.NORMAL
            msg += "Normal"
        self.UI.MsgLine.SetTemporary(msg)

    def UserBreak(self):
        self.UI.PrintLine("\n\n")
        Logger.Info(f"Breaking on user demand.")
        self.Finishing = True

    def PrepareUI(self):
        self.UI.NonDestructive = Config.NonDestructivePrint
        self.UI.MinLen = 79

    def GetTotalElapsedTime(self):
        return time.time() - self.StartTime

    def GetRunningElapsedTime(self):
        if self.Paused:
            return self.PausedAt - self.StartTime - self.PausedTime
        return self.GetTotalElapsedTime() - self.PausedTime

    def GetPausedTime(self):
        ret = self.PausedTime
        if self.Paused:
            ret += time.time() - self.PausedAt
        return ret

    def CalculateESA(self):
        ETA = 0
        AvgETA = 0

        if self.SimStats.StepETA > 0:
            ETA = self.SimStats.StepETA
            if self.SimStats.TimeETA > 0:
                ETA += self.SimStats.TimeETA
                ETA /= 2
        else:
            ETA = self.SimStats.TimeETA

        if self.SimStats.AvgStepETA > 0:
            AvgETA = self.SimStats.AvgStepETA
            if self.SimStats.AvgTimeETA > 0:
                AvgETA += self.SimStats.AvgTimeETA
                AvgETA /= 2
        else:
            AvgETA = self.SimStats.AvgTimeETA

        #print(f"SimStats.StepsLeft: {self.SimStats.StepsLeft}, AccStats.DataStepSpeed: {self.AccStats.DataStepSpeed}")
        if self.SimStats.StepsLeft >= 0 and self.AccStats.DataSpeedStep >= 0:
            self.AccStats.StepESA = self.AccStats.DataSize + self.SimStats.StepsLeft * self.AccStats.DataSpeedStep

        #print(f"SimStats.TimeETA: {self.SimStats.TimeETA}, AccStats.DataSpeed: {self.AccStats.DataSpeed}")
        if ETA >= 0 and self.AccStats.DataSpeed >= 0:
            self.AccStats.TimeESA = self.AccStats.DataSize + ETA * self.AccStats.DataSpeed

        if self.SimStats.StepsLeft >= 0 and self.AccStats.AvgDataSpeedStep >= 0:
            self.AccStats.AvgStepESA = self.AccStats.DataSize + self.SimStats.StepsLeft * self.AccStats.AvgDataSpeedStep

        if AvgETA >= 0 and self.AccStats.AvgDataSpeed >= 0:
            self.AccStats.AvgTimeESA = self.AccStats.DataSize + AvgETA * self.AccStats.AvgDataSpeed

        if ETA >= 0:
            self.StorageStats.ESA = self.StorageStats.Size + self.StorageStats.Speed * ETA

        if AvgETA >= 0:
            self.StorageStats.AvgESA = self.StorageStats.Size + self.StorageStats.Speed * AvgETA


    def Update(self, Force = False):
        if self.StorageStats.StartSize < 0:
            self.StorageStats.StartSize = DirSize(Config.StoragePath)
        if self.UpdateTimer.Expired() or Force:
            if self.State.MainUpdated and self.State.SecondUpdated:
                self.State.MainUpdated = False
                self.State.SecondUpdated = False
            self.SimStats.PausedTime = self.GetPausedTime()
            self.AccStats.PausedTime = self.SimStats.PausedTime
            self.StorageStats.PausedTime = self.SimStats.PausedTime
            self.AccStats.Recalculate()
            self.CalculateESA()
            if self.WarpxProcess != None:
                    #print("Update proc info.")
                try:
                    self.ProcStats = Processes.GetTreeStats(self.WarpxProcess)
                except pypsutil.NoSuchProcess as e:
                    self.WarpxProcess = None
                self.AccStats.CPUStart = self.ProcStats.CrTime
                self.AccStats.CPUTime = self.ProcStats.CPU
                self.UI.ProcStats = self.ProcStats
                    #print(str(self.ProcStats))
            if not Config.Quiet:
                self.UI.Rewrite()
            self.UpdateTimer.Reset()
        if self.StorageTimer.Expired():
            self.StorageStats.RawSize = DirSize(Config.StoragePath)
            self.StorageStats.Recalculate()
            self.StorageTimer.Reset()

PrintParams()

WW = WarpxWrapper()
WW.PrepareSource()
WW.PrepareDataStream()
WW.PrepareUI()
WW.RegisterActions()
WW.PrepareLogOutput()
WW.ActivateStreams()

if Config.DontRun:
    exit(0)

WW.WaitForDataStart = time.time()
Logger.Debug("\n      Start waiting for WarpX Data...\n")

print("\n")

if WW.WarpxProcess == None and Config.PID > 0:
    try:
        WW.WarpxProcess = pypsutil.Process(Config.PID)
    except Exception as e:
        Logger.ExceptError(e)
        Logger.Error(f"Cannot assign Warpx process from given PID: {Config.PID}")


try:
    WW.ControlInput.DisableBuffering()

    while 1:
        if Config.SkipMain:
            Logger.Debug("Skipping main.")
            break

        WW.Update()

        while not WW.EventQueue.empty():
            WW.EventQueue.get_nowait() # eat stalled events

        WW.ProcessControlInput()

        if WW.Finishing:
            if WW.StartTime < 0:
                WW.StartTime = time.time()
            break

        if WW.StartTime < 0:
            WaitingFor = time.time() - WW.WaitForDataStart
            if WaitingFor > 0:
                WW.UI.PrintStaticLine(f"   Waiting for WarpX to start sending data for: {WW.UI.FmtTime.Str(WaitingFor)}")

        #if not (Header or Footer):
        #    WW.UI.Update()

        OutputLine = WW.DataInput.Read()
        if OutputLine == None or OutputLine == "":
            #print("Read null string")
            if (WW.DataInput.IsActive()):
#                print(f"DataInput active, waiting for {Config.UpdateInterval}.")
                Event = None
                try:
                    Event = WW.EventQueue.get(timeout=Config.UpdateInterval)
                except Exception as e:
                    #Logger.Debug("Exception while waiting for event.")
                    #Logger.ExceptDebug(e)
                    pass
#                t = type(Event)
#                print("Got event:", Event, t)
#                if t == float:
#                    print("Time delay:", time.time() - Event)
                continue # So all interactivity must take place earlier
            else:
                Logger.Debug("DataInput inactive, finishing.")
                break

        WW.AccStats.DataSize += len(OutputLine)
        #print(f"Increasing data size: {AccStats.DataSize}.")

        if not WW.State.ThirdUpdated and WW.WarpxProcess == None and Config.Source == SourceType.FILE and Config.PID == 0:
            Ps = Processes.FileUsers(Config.InputFile, ["w", "a"])
#            print("")
#            print(Ps)
            Me = pypsutil.Process()
            for P in Ps:
                if P != Me:
                    WarpxProcess = P
                    Logger.Debug(f"Detected Warpx process: {WW.WarpxProcess.name()} ({WarpxProcess.pid}).")
            if WW.WarpxProcess == None:
                Logger.Warning("Warpx process not detected!")
            WW.State.ThirdUpdated = True


        if WW.StartTime < 0:
            WW.StartTime = time.time()
            WW.UI.CurrentSection = UI.Section.HEADER
            WW.UI.PrintLine("\n   Got data, starting processing.")

        if WW.LogOutput != None:
            WW.LogOutput.Write(OutputLine)

        if not WW.State.Footer and not WW.State.MainUpdated and Re1.search(OutputLine):
            WW.State.Header = False # Just in case we missed something
            nums = ReNum.findall(OutputLine)

            WW.SimStats.Step = int(nums[0])
            WW.AccStats.Step = int(nums[0])
            WW.SimStats.Time = float(nums[1])
            WW.SimStats.TimeDelta = float(nums[2])

            WW.SimStats.Recalculate()
            WW.AccStats.RecalculateStep()

            WW.State.MainUpdated = True

        elif not WW.State.SecondUpdated and Re2.search(OutputLine):
            nums = ReNum.findall(OutputLine)
        #print(nums)

            WW.SimStats.ElapsedInternalRealTime = float(nums[0])
            WW.SimStats.InternalRealTimeDelta = float(nums[1])
            WW.State.SecondUpdated = True

        elif WW.State.Header == True and ReHead.match(OutputLine):
            WW.UI.CurrentSection = UI.Section.MAIN
            WW.State.Header = False
            PrefixLen = len(ReHeadStr)
            WW.ParseUsedInput(OutputLine[PrefixLen:len(OutputLine) - 1])

        elif WW.State.Footer == False and ReFoot.match(OutputLine):
            WW.State.Footer = True
            WW.UI.CurrentSection = UI.Section.FOOTER
            Logger.Debug("Footer detected.")
            if Config.SkipFooter:
                break
            time.sleep(Config.UpdateInterval) # Let some time to the pipe to read last of data.
            WW.DataInput.Interval = 0 # Don't wait for data anymore.
        elif ReAbort.match(OutputLine):
            Logger.Warning("Warpx aborted.")
            break

        if WW.State.Header or WW.State.Footer:
            print(OutputLine, end='')

except Exception as e:
    Logger.Critical("Unhandled exception, breaking main loop.")
    Logger.ExceptCrit(e)

WW.ControlInput.RestoreBuffering()

WW.UI.CurrentSection = UI.Section.FOOTER

"""print(MeanStepETA, MeanTimeETA, MeanTest, Steps)

MeanStepETA /= Steps
MeanTimeETA /= Steps
MeanTest /= Steps

print(MeanStepETA, MeanTimeETA, MeanTest)"""
#WW.DeactivateStreams()  # This will most probably hang
WW.CloseStreams()

if Config.AbortOnExit and WW.WarpxProcess != None:
    WW.WarpxProcess.terminate()

#EMsg = "Mean ETA: {0} / {1}".format(datetime.timedelta(seconds=MeanStepETA), datetime.timedelta(seconds=MeanTimeETA))
#EMsg = "|{:^77}|".format(EMsg)
if not Config.Quiet:
    WW.UI.WriteSummary(WW.GetRunningElapsedTime())
