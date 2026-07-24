#!/usr/bin/python -u

import sys
import os
import subprocess
import regex
import time
import datetime
import pathlib
import enum
import argparse
import signal
import shutil
import stat
import pypsutil
from blessed import Terminal
from queue import SimpleQueue

from FormattedValue import FormattedNumber, FormattedTime, SizeStr
from NonBlockingStream import InputStream, InputTerminal
import FitLine
from MessageLine import MessageLine
from Timer import Timer
from Various import CompareKeys
from Logger import Logger, Verbosity
import Processes

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
    DontRun = False

    LogFile = "Log.txt"

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

    BreakKey = 27
    ISOKey = "f"
    NDestPrintKey = "d"
    PauseKey = ' '

Params = []

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

def CreateExecEnv():
    Ret = {
        "Verbosity" : Verbosity,
        "SourceType" : SourceType,
        "getLogLevel" : getLogLevel,
        "setLogLevel" : setLogLevel
        }
    cd = vars(Config)
    for name in cd:
        if name[:2] != "__" and name != "LogLevel":
            Ret[name] = cd[name]
    return Ret

def SyncConfig(glob):
    global Config
    cd = vars(Config)
    for name in cd:
        if name[:2] != "__" and name != "LogLevel" and name in glob:
            setattr(Config, name, glob[name])

def IncludeFile(fname):
    Logger.Debug(f"Including file '{fname}'.")
    try:
        f = open(fname, "r")
    except Exception as e:
        Logger.Error(f"Cannot open file '{fname}'.")
        Error(1, e)
        return
    prog = f.read()
    env = CreateExecEnv()
    mod = {}
    try:
        exec(prog, env, mod)
    except Exception as e:
        Logger.Error(f"Error while executing include file: '{fname}'")
        Logger.ExceptError(1, e)
        Error()
    finally:
        SyncConfig(mod)

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
    for name in Params:
        PrintParam(name, Config.MaxParamLength)

parser = argparse.ArgumentParser(
        description = "Small script for showing realtime WarpX time and progress stats and (optionally) to help running it."
    )

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

class IncludeAction(argparse.Action):
    Used = False
    def __call__(self, parser, namespace, value, option_string):
        if type(value) == str:
            IncludeFile(value)
        else:
            for name in value:
                IncludeFile(name)
        self.__class__.Used = True

parser.add_argument("-I", "--include", nargs='+', action=IncludeAction)

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
#parser.add_argument("-s", "--source", nargs=1, action=SourceAction, choices=Sources.keys())

def StrToBool(value):
    try:
#        print("Try conversion to float: ", value)
        value = float(value)
#        print("Success: ", value, type(value))
        if value > 0:
            value = True
        else:
            value = False
#        print("Still successful.")
    except Exception:
#        print("Not successful. Trying again: ", value)
        value = distutils.util.strtobool(value)
        if value > 0:
            value = True
        else:
            value = False
    return value

def StrToType(value, t):
    if t == bool:
        return StrToBool(value)
    return t(value)

class ParamAction(argparse.Action):
    Param = ""
    UnpackList = False
    def __init__(self, option_strings, dest, **kwargs):
#        print("{}.__init__({}, {}, {}, {})".format(self.__class__.__name__, option_strings, dest, nargs, kwargs))
        self.Param = kwargs.pop("VarName")
        if kwargs["nargs"] == 1:
            self.UnpackList = True
        super().__init__(option_strings, dest, **kwargs)
    def __call__(self, parser, namespace, values, option_string):
        """if type(values) == list:
            print("List?", values)
            value = values[0]
        else:
            value = values"""
        global Config
        value = values
        t = type(getattr(Config, self.Param))
        if self.UnpackList and type(value) == list:
            value = value[0]
        try:
            value = StrToType(value, t)
        except:
            Error("Value of param {} must be convertable to {}!".format(option_string, t.__name__))
        setattr(Config, self.Param, value)
        Logger.Debug("Command line: set {} to {}".format(self.Param, value))

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

def AddParam(VarName, *Args, **KArgs):
    global Config
    v = getattr(Config, VarName)
    if v != None:
        global parser
        if not "nargs" in KArgs:
            KArgs["nargs"] = '?' if "const" in KArgs else 1
        if not "action" in KArgs:
            KArgs["action"] = ParamAction
        if not "help" in KArgs:
            KArgs["help"] = "Type: {}.".format(TypeDescription(type(v), True))
        parser.add_argument(*Args, VarName = VarName, **KArgs)
        Params.append(VarName)

        Config.MaxParamLength = max(Config.MaxParamLength, len(VarName))
    else:
        raise NameError("Variable {VarName} not found.")

AddParam("LogLevel", "-v", "--verbosity", action=VerbosityAction, const='debug', choices=LogLevels.keys())
AddParam("Quiet", "-q", "--quiet", const = True)
AddParam("DontRun", "-r", "--dont-run", const = True)
AddParam("ErrorIsFatal", "--error-fatal", const = True)
AddParam("LogFile", "-l", "--log-file")
AddParam("NonDestructivePrint", "-d", "--non-destructive-print", const = True)
AddParam("UpdateInterval", "-u", "--upd-int", "--update-interval")
AddParam("MaxStep", "-x", "--max-steps")
AddParam("MaxTime", "-t", "--max-time")
AddParam("SkipMain", "-a", "--skip-main-loop", const = True)
AddParam("SkipFooter", "-f", "--skip-footer", const = True)
AddParam("DontWaitForFooter", "--dont-wait-for-footer", const = True)
AddParam("Source", "-s", "--source", action=SourceAction, choices=Sources.keys())
AddParam("PID", "-p", "--pid")
AddParam("AbortOnExit", "-k", "--abort-on-exit", const = True)
AddParam("InputFile","-i", "--input-file")
AddParam("IsFifo", "--fifo", "--pipe", const = True)
AddParam("ExecBase", "--exec-base")
AddParam("ExecDim", "--dim", "--exec-dim")
AddParam("Executable", "--executable")
AddParam("UseMpi", "-m", "--use-mpi", const = True)
AddParam("Command", "-c", "--command", nargs="+")
parser.add_argument("command", nargs="*")

DefaultConfigFile = "config.py"
if IsReadable(DefaultConfigFile): # Always try, never cry.
    IncludeFile(DefaultConfigFile)
else:
    Logger.Debug(f"Cannot read default config file: '{DefaultConfigFile}'")

args = parser.parse_args(sys.argv[1:])
if len(args.command) > 0:
    if type(Command) == list:
        Command.extend(args.command)
    else:
        Command = args.command

LogStream = None
LogWritable = False

def PrepareLogging():
    global LogStream
    global LogWritable
    if Config.LogFile != "":
        try:
            LogStream = open(Config.LogFile, "w")
            LogWritable = True
        except Exception as e:
            Logger.Error(f"An exception occured while opening the log file '{Config.LogFile}':")
            Error(1, e)
            LogWritable = False

#DataStream = None
#IsFifo = False

DataInput = InputStream(Lines = True)

def PrepareStdin():
#    global DataStream
#    global IsFifo
#    DataStream = sys.stdin
#    IsFifo = True
    global DataInput
    DataInput.Input = sys.stdin

def PrepareInputFileName():
#    global DataStream
#    global IsFifo
    global DataInput
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
        DataInput.Stream = Config.InputFile
    else:
        Logger.Debug("Input fle is an ordinary file. Don't exit if read zero bytes.")
        DataInput.Interval = Config.UpdateInterval
        try:
            DataStream = open(Config.InputFile, "r")
        except Exception as e:
            Logger.ExceptCritic(e)
            Fatal(f"Cannot open data file '{Config.InputFile}' for reading.")
        DataInput.Stream = DataStream
        Logger.Debug(f"File '{Config.InputFile}' successfully opened.")

WarpxProcess = None

def PrepareCommand():
    global Command
    global InputFileName
    global WarpxProcess

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
        WarpxProcess = pypsutil.Popen(args=CmdArgs,
                                    stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT,
                                    text=True)
    except Exception as e:
        Logger.ExceptCrit(e)
        Fatal("Cannot create a subprocess to get its output.")

    DataInput.Stream = WarpxProcess.stdout

PrintParams()

if Config.Source == SourceType.STDIN:
    PrepareStdin()
elif Config.Source == SourceType.FILE:
    PrepareInputFileName()
else:
    PrepareCommand()

PrepareLogging()

FmtNmb = FormattedNumber()
FmtTime = FormattedTime()
FmtNmb.ForbidNegative = True

StartTime = -1

class SimulationStats:
    Step = -1 # These two are replenished externally
    Time = -1

    MaxStep = -1 # These two are set once at the beginning
    MaxTime = -1

    StepsLeft = -1
    TimeLeft = -1

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

    ElapsedInternalRealTime = -1
    InternalRealTimeDelta = -1

    ElapsedRealTimeEfficiency = -1
    RealTimeDeltaEfficiency = -1

    def __init__(self, MaxStep, MaxTime):
        self.MaxStep = MaxStep
        self.MaxTime = MaxTime
        self.StartRealTime = time.time()
        self.Updated = False

    def CalculateETA(self):
        self.StepDelta = self.Step - self.PrevStep
        # TimeDelta was provided externally, but is no longer
        self.TimeDelta = self.Time - self.PrevTime

        self.RealTimeDelta = self.CurrentRealTime - self.PrevRealTime

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
        self.AvgStepETA = self.AvgStepSpeed * self.StepsLeft

        self.AvgTimeSpeed = self.Time / self.ElapsedRealTime
        self.AvgTimeETA = self.AvgTimeSpeed * self.TimeLeft

    def Recalculate(self, Time = None):
        if self.Step <= self.PrevStep:
            Logger.Warning(f"Step {self.Step} <= last step: {self.PrevStep}. Nothing to calculate.")
            return
        if Time == None:
            Time = time.time()

#        print(f"TimeDelta: {self.TimeDelta}, StepDelta: {self.StepDelta}")

        self.CurrentRealTime = Time
        self.ElapsedRealTime = self.CurrentRealTime - self.StartRealTime

        if self.Step >= 0 and self.MaxStep > 0:
            self.StepsLeft = self.MaxStep - self.Step

        if self.Time >= 0 and self.MaxTime > 0:
            self.TimeLeft = self.MaxTime - self.Time

        self.StepsProgress = int((self.Step / self.MaxStep) * 100)
        self.TimeProgress = int((self.Time / self.MaxTime) * 100)

        self.CalculateETA()
        self.CalculateAvgETA()

        if self.ElapsedRealTime > 0:
            self.ElapsedRealTimeEfficiency = int((self.ElapsedInternalRealTime /  self.ElapsedRealTime) * 100)
        if self.RealTimeDelta > 0:
            self.RealTimeDeltaEfficiency = int((self.InternalRealTimeDelta / self.RealTimeDelta) * 100)

        self.PrevStep = self.Step
        self.PrevTime = self.Time
        self.PrevRealTime = self.CurrentRealTime
        self.Updated = True

class DataStats:
    UpdNr = 0
    Step = 0
    LastStep = 0
    DataSize = 0
    PrevDataSize = 0
    PrevStepDataSize = 0

    StartTime = -1
    Elapsed = 0

    CurrentTime = 0
    PrevTime = 0

    DataSpeed = 0
    TotalDataSpeed = 0

    DataStepSpeed = 0
    TotalDataStepSpeed = 0

    StepESA = -1
    TimeESA = -1

    TotalStepESA = -1
    TotalTimeESA = -1

    def Recalculate(self):
        self.UpdNr += 1
        self.CurrentTime = time.time()
        if self.StartTime < 0:
            self.StartTime = self.CurrentTime
        self.Elapsed = self.CurrentTime - self.StartTime
        #print(f"Upd # {self.UpdNr}. Loop: {self.Loop}.")
        #print(f"CTime: {self.CurrentTime:.2f}, prev time: {self.PrevTime:.2f}")

        self.Delta = self.CurrentTime - self.PrevTime
        self.DataDelta = self.DataSize - self.PrevDataSize

        if self.Delta > 0:
            self.DataSpeed = self.DataDelta / self.Delta

        if self.Elapsed > 0:
            self.TotalDataSpeed = self.DataSize / self.Elapsed

        self.PrevTime = self.CurrentTime
        self.PrevDataSize = self.DataSize
        #print(f"DDelta: {self.DataDelta} / {self.Delta:.2f}, {self.DataSpeed:.2f}/s")

    def RecalculateStep(self):
        if self.Step <= self.LastStep:
            Logger.Warning(f"Step: {self.Step} <= LastStep: {self.LastStep}. Nothing to calculate.")
            return

        self.StepDelta = self.Step - self.LastStep
        self.DataStepDelta = self.DataSize - self.PrevStepDataSize
        if self.DataStepDelta > 0:
            self.DataStepSpeed = self.DataStepDelta / self.StepDelta
        if self.Step > 0:
            self.TotalDataStepSpeed = self.DataSize / self.Step
        self.LastStep = self.Step

class UI:
    class Section(enum.Enum):
        WAIT = 0
        HEADER = 1
        MAIN = 2
        FOOTER = 3

    Destructive = True
    MinLen = 0
    MaxLen = 0
    Avg = True
    CurrentSection = Section.WAIT

    SimStatsHeight = 7
    DataStatsHeight = 3
    MessageLineHeight = 1

    def __init__(self, SimStats, DataStats):
        self.Terminal = Terminal()
        print(self.Terminal.clear_bol)
        self.First = True
        self.SimStats = SimStats
        self.DataStats = DataStats
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

    def PrintLine(self, Text, End = "\n"):
        print(Text + self.Terminal.clear_eol, end = End)

    def GetSimSpeeds(self):
        if self.Avg:
            return self.SimStats.AvgStepSpeed, self.SimStats.AvgTimeSpeed
        return self.SimStats.StepSpeed, self.SimStats.TimeSpeed

    def GetSimETAs(self):
        if self.Avg:
            return self.SimStats.AvgStepETA, self.SimStats.AvgTimeETA
        return self.SimStats.StepETA, self.SimStats.TimeETA

    def WriteHeader(self):
        lmin, lmax = self.GetLen()
#        print(lmin, lmax, Length)
        d = self.Destructive
        self.PrintLine("+" + "-" * (lmin - 2) + "+")
        fmt = f"|{{:^{lmin - 2}}}|"
        self.PrintLine(fmt.format("Time statistics:"))
        self.PrintLine("+" + "-" * (lmin - 2) + "+")
        print("|")
        print("\n\n\n")

    def WriteSimStats(self):
        s = self.SimStats # Less to write
        minl, maxl = self.GetLen()
        SSSpeed, STSpeed = self.GetSimSpeeds()
        SETA, TETA = self.GetSimETAs()
        s1 = f"|   Step:  {FmtNmb.Str(s.Step):^15} / {FmtNmb.Str(s.MaxStep):^15} : {FmtNmb.Str(s.StepsLeft):^15} ({FmtNmb.Str(s.StepsProgress):>3}%)," +\
        f"x{FmtNmb.Str(SSSpeed):>9}, ETA: {FmtTime.Str(SETA):>20}"

        s2 = f"|   Sim time: {FmtTime.Str(s.Time):^12} / {FmtTime.Str(s.MaxTime):^15} : {FmtTime.Str(s.TimeLeft):^15} ({FmtNmb.Str(s.TimeProgress):>3}%)," +\
        f"x{FmtNmb.Str(STSpeed):>9}, ETA: {FmtTime.Str(TETA):>20}"

        s3 = f"|   Elapsed: {FmtTime.Str(s.ElapsedRealTime)}, delta: {FmtTime.Str(s.RealTimeDelta)} ({FmtTime.Str(s.TimeDelta * s.RealTimeDelta)}), eff: elapsed: {s.ElapsedRealTimeEfficiency}%, delta: {s.RealTimeDeltaEfficiency}%"

#        if not self.NonDestructive:
#            print('\r\033[A\033[A\033[A\033[A\033[A', end='')
        self.PrintLine(s1)
        self.PrintLine(s2)
        self.PrintLine(s3)
        self.PrintLine("|")
        s.Updated = False

    def WriteDataStats(self):
        s = self.DataStats
        minl, maxl = self.GetLen()
        self.PrintLine("+" + "-" * (minl - 2) + "+")
        self.PrintLine(f"|   Data: {SizeStr(s.DataSize):>9}, {SizeStr(s.DataSpeed):>8}/s (avg: {SizeStr(s.TotalDataSpeed):>8}/s) |"
                       f"{SizeStr(s.DataStepSpeed):>8}/st (avg: {SizeStr(s.TotalDataStepSpeed):>8}/st) |"
                       f" ESA: {SizeStr(s.TimeESA):>8}/{SizeStr(s.StepESA):>8} (avg: {SizeStr(s.TotalTimeESA):>8}/{SizeStr(s.TotalStepESA):>8}).")


    def WriteMessageLine(self):
        minl, maxl = self.GetLen()
        self.PrintLine(f"+{self.MsgLine.GetLine(LineLen = minl - 2)}+")

    def Rewrite(self, Force):
        self.CacheMaxLen()
        if self.CurrentSection != self.Section.MAIN:
            return
        with self.Terminal.no_line_wrap():
            MoveUp = 0
            if self.First:
                self.WriteHeader()
                self.First = False
            else:
                if self.SimStats.Updated or Force:
                    MoveUp = self.SimStatsHeight
                else:
                    MoveUp = self.DataStatsHeight
#            print(f"MoveUp: {MoveUp}")
            if MoveUp and not self.NonDestructive:
                print(self.Terminal.move_up(MoveUp + 1))
            if self.SimStats.Updated or Force:
                self.WriteSimStats()
            self.WriteDataStats()
            self.WriteMessageLine()

class WarpxWrapper:
    UpdateInterval = 0.5

    def __init__(self, Interval, MaxStep, MaxTime):
        self.UpdateInterval = Interval
        self.SimStats = SimulationStats(MaxStep, MaxTime)
        self.DataStats = DataStats()
        self.UI = UI(self.SimStats, self.DataStats)
        self.Timer = Timer(self.UpdateInterval)

    def CalculateESA(self):
        #print(f"SimStats.StepsLeft: {self.SimStats.StepsLeft}, DataStats.DataStepSpeed: {self.DataStats.DataStepSpeed}")
        if self.SimStats.StepsLeft >= 0 and self.DataStats.DataStepSpeed >= 0:
            self.DataStats.StepESA = self.DataStats.DataSize + self.SimStats.StepsLeft * self.DataStats.DataStepSpeed

        #print(f"SimStats.TimeETA: {self.SimStats.TimeETA}, DataStats.DataSpeed: {self.DataStats.DataSpeed}")
        if self.SimStats.TimeETA >= 0 and self.DataStats.DataSpeed >= 0:
            self.DataStats.TimeESA = self.DataStats.DataSize + self.SimStats.TimeETA * self.DataStats.DataSpeed

        if self.SimStats.StepsLeft >= 0 and self.DataStats.TotalDataStepSpeed >= 0:
            self.DataStats.TotalStepESA = self.DataStats.DataSize + self.SimStats.StepsLeft * self.DataStats.TotalDataStepSpeed

        if self.SimStats.TimeETA >= 0 and self.DataStats.TotalDataSpeed >= 0:
            self.DataStats.TotalTimeESA = self.DataStats.DataSize + self.SimStats.TimeETA * self.DataStats.TotalDataSpeed

    def UpdateUI(self, Force = False):
        if self.Timer.Expired() or Force:
            if not Config.Quiet:
                self.UI.Rewrite(Force)


    def Update(self, Force = False):
        if self.Timer.Expired() or Force:
            #self.SimStats.Recalculate() # only if there are new step data avaliable.
            self.DataStats.Recalculate()
            self.CalculateESA()
            if not Config.Quiet:
                self.UI.Rewrite(Force)
            self.Timer.Reset()

Header = True
Footer = False
SkipMain = False

MainUpdated = False
SecondUpdated = False
ThirdUpdated = False

Paused = False

MeanStepETA = 0
MeanTimeETA = 0
UpdateCount = 0

Re1     = regex.compile("TIME")
Re2     = regex.compile("Evolve time")
ReHead  = regex.compile("For full input parameters, see the file\\:")
ReFoot  = regex.compile("Total Time")
ReAbort = regex.compile("MPI_ABORT")
ReNum   = regex.compile("[+-]?(?:[0-9]+(?:\\.[0-9]+)?|\\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
#ReNum = regex.compile("[0-9]+(.[0-9]+(e[+-][0-9]+)?)?")

WaitForDataStart = time.time()
Logger.Debug("\n      Start waiting for WarpX Data...\n")

if Config.DontRun:
    exit(0)

EventQueue = SimpleQueue()

WarpxWr = WarpxWrapper(Config.UpdateInterval, Config.MaxStep, Config.MaxTime)
WarpxWr.UI.NonDestructive = Config.NonDestructivePrint
WarpxWr.UI.MinLen = 79
MainTimer = Timer(Config.UpdateInterval)

ControlInput = InputTerminal(WarpxWr.UI.Terminal, EventQueue)
if Config.Source == SourceType.STDIN: # Sorry, not interactive mode (or use another i/o stream)
    ControlInput.Stream = None

DataInput.EventQueue = EventQueue
DataInput.Event = False
DataInput.QueueSizeThreshold = 100

Logger.Debug("Activating input non-blocking pipe.")
DataInput.Activate()
Logger.Debug(1, f"Pipe activity status: {DataInput.IsActive()}.")

if ControlInput.Stream != None:
    Logger.Debug("Activating stdin non-blocking pipe.")
    ControlInput.Activate()
    Logger.Debug(1, f"Pipe activity status: {ControlInput.IsActive()}.")

print("\n")

Finishing = False

if WarpxProcess == None and Config.PID > 0:
    try:
        WarpxProcess = psutil.Process(Config.PID)
    except Exception as e:
        Logger.ExceptError(e)
        Logger.Error(f"Cannot assign Warpx process from given PID: {Config.PID}")

try:
    ControlInput.DisableBuffering()

    while 1:
        if SkipMain:
            Logger.Debug("Skipping main.")
            break

        WarpxWr.Update()

        while not EventQueue.empty():
            EventQueue.get_nowait() # eat stalled events

        while 1:
            key = ControlInput.Read()
            if key == None:
                break
#            print("Got key:", key, type(key))
            if CompareKeys(key, Config.BreakKey):
                print("\n\n")
                Logger.Info(f"Breaking on user demand.")
                Finishing = True
                break
            if CompareKeys(key, Config.ISOKey):
                FmtTime.ISO = not FmtTime.ISO
                msg = "ISO "
                if FmtTime.ISO:
                    msg += "set"
                else:
                    msg += "unset"
                WarpxWr.UI.MsgLine.SetTemporary(msg)
            elif CompareKeys(key, "a"):
                WarpxWr.UI.Avg = not WarpxWr.UI.Avg
                WarpxWr.UI.MsgLine.SetTemporary(f"Avg: {WarpxWr.UI.Avg}")
            elif CompareKeys(key, Config.NDestPrintKey):
                WarpxWr.UI.NonDestructive = not WarpxWr.UI.NonDestructive
            elif CompareKeys(key, Config.PauseKey):
                if Paused:
                    if WarpxProcess != None:
                        Processes.ResumeTree(WarpxProcess)
                    Paused = False
                    WarpxWr.UI.MsgLine.SetPersistent()
                    WarpxWr.UI.MsgLine.SetTemporary("Resumed")
                else:
                    if WarpxProcess != None:
                        Processes.PauseTree(WarpxProcess)
                    Paused = True
                    WarpxWr.UI.MsgLine.SetPersistent("Paused")
            else:
                WarpxWr.UI.MsgLine.SetTemporary(key)
            WarpxWr.UpdateUI(True)

        if Finishing:
            if StartTime < 0:
                StartTime = time.time()
            break

        if StartTime < 0:
            WaitingFor = time.time() - WaitForDataStart
            if WaitingFor > 0:
                End = ''
                Start = ''
                if Config.NonDestructivePrint:
                    End = '\n'
                else:
                    Start = '\r'
                WarpxWr.UI.PrintLine(f"{Start}   Waiting for WarpX to start sending data for: {FmtTime.Str(WaitingFor)}", End)

        #if not (Header or Footer):
        #    WarpxWr.UI.Update()

        OutputLine = DataInput.Read()
        if OutputLine == None:
            #print("Read null string")
            if (DataInput.IsActive()):
#                print(f"DataInput active, waiting for {Config.UpdateInterval}.")
                Event = None
                try:
                    Event = EventQueue.get(timeout=Config.UpdateInterval)
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

        WarpxWr.DataStats.DataSize += len(OutputLine)
        #print(f"Increasing data size: {DataStats.DataSize}.")

        if not ThirdUpdated and WarpxProcess == None and Config.Source == SourceType.FILE and Config.PID == 0:
            Ps = Processes.FileUsers(Config.InputFile, ["w", "a"])
#            print("")
#            print(Ps)
            Me = pypsutil.Process()
            for P in Ps:
                if P != Me:
                    WarpxProcess = P
                    Logger.Debug(f"Detected Warpx process: {WarpxProcess.name()} ({WarpxProcess.pid}).")
            if WarpxProcess == None:
                Logger.Warning("Warpx process not detected!")
            ThirdUpdated = True


        if StartTime < 0:
            StartTime = time.time()
            WarpxWr.UI.CurrentSection = UI.Section.HEADER
            print("\n   Got data, starting processing.\n")

            if LogWritable:
                try:
                    LogStream.write(OutputLine)
                except Exception as e:
                    warning("An error while writing to log file.")
                    warning(1, e)

        if not Footer and not MainUpdated and Re1.search(OutputLine):
            Header = False # Just in case we missed something
            nums = ReNum.findall(OutputLine)

            WarpxWr.SimStats.Step = int(nums[0])
            WarpxWr.DataStats.Step = int(nums[0])
            WarpxWr.SimStats.Time = float(nums[1])
            WarpxWr.SimStats.TimeDelta = float(nums[2])

            WarpxWr.SimStats.Recalculate()
            WarpxWr.DataStats.RecalculateStep()

            MainUpdated = True

        elif not SecondUpdated and Re2.search(OutputLine):
            nums = ReNum.findall(OutputLine)
        #print(nums)

            WarpxWr.SimStats.ElapsedInternalRealTime = float(nums[0])
            WarpxWr.SimStats.InternalRealTimeDelta = float(nums[1])
            SecondUpdated = True

        elif Header == True and ReHead.match(OutputLine):
            WarpxWr.UI.CurrentSection = UI.Section.MAIN
            Header = False

        elif Footer == False and ReFoot.match(OutputLine):
            Footer = True
            WarpxWr.UI.CurrentSection = UI.Section.FOOTER
            Logger.Debug("Footer detected.")
            if Config.SkipFooter:
                break
            time.sleep(Config.UpdateInterval) # Let some time to the pipe to read last of data.
            DataInput.Interval = 0 # Don't wait for data anymore.
        elif ReAbort.match(OutputLine):
            Logger.Warning("Warpx aborted.")
            break

        if Header or Footer:
            print(OutputLine, end='')

        if MainUpdated and SecondUpdated:
            if MainTimer.Expired():
                MainTimer.Reset()
                MainUpdated = False
                SecondUpdated = False
                #ThirdUpdated = False Do it only once

except Exception as e:
    Logger.Critical("Unhandled exception, restoring terminal settings.")
    ControlInput.RestoreBuffering()
    Logger.ExceptCrit(e)
    exit(1)

ControlInput.RestoreBuffering()

WarpxWr.UI.CurrentSection = UI.Section.FOOTER

"""print(MeanStepETA, MeanTimeETA, MeanTest, Steps)

MeanStepETA /= Steps
MeanTimeETA /= Steps
MeanTest /= Steps

print(MeanStepETA, MeanTimeETA, MeanTest)"""

if Config.AbortOnExit and PID > 0:
    os.kill(PID, signal.SIGABRT)

FMsg = "Finished in " + FmtTime.Str(time.time() - StartTime)
FMsg = f"|{FMsg:^77}|"

#EMsg = "Mean ETA: {0} / {1}".format(datetime.timedelta(seconds=MeanStepETA), datetime.timedelta(seconds=MeanTimeETA))
#EMsg = "|{:^77}|".format(EMsg)

print("")
print("+-----------------------------------------------------------------------------+")
print("|                                                                             |")
print(FMsg)
#print(EMsg)
print("|                                                                             |")
print("+-----------------------------------------------------------------------------+")
print()
