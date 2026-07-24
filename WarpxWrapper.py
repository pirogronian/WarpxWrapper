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

    MaxSteps = -1
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
AddParam("MaxSteps", "-x", "--max-steps")
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

    MaxSteps = -1 # These two are set once at the beginning
    MaxTime = -1

    LeftSteps = -1
    LeftTime = -1

    StepsProgress = -1
    TimeProgress = -1

    CurrentRealTime = 0 # This is replenished automatically
    PreviousRealTime = 0

    StartRealTime = 0
    ElapsedRealTime = 0

    PreviousStep = 0

    StepDelta = -1
    TimeDelta = -1 # This also is replenished externally
    RealTimeDelta = -1

    StepSpeed = 0
    TimeSpeed = 0

    StepETA = -1
    TimeETA = -1

    ElapsedInternalRealTime = -1
    InternalRealTimeDelta = -1

    ElapsedRealTimeEfficiency = -1
    RealTimeDeltaEfficiency = -1

    def __init__(self, MaxSteps = -1, MaxTime = -1):
        self.MaxSteps = MaxSteps
        self.MaxTime = MaxTime
        self.StartRealTime = time.time()
        self.Updated = False

    def Recalculate(self, Time):
        self.CurrentRealTime = Time
        self.ElapsedRealTime = self.CurrentRealTime - self.StartRealTime

        if self.Step >= 0 and self.MaxSteps > 0:
            self.LeftSteps = self.MaxSteps - self.Step

        if self.Time >= 0 and self.MaxTime > 0:
            self.LeftTime = self.MaxTime - self.Time

        self.StepsProgress = int((self.Step / self.MaxSteps) * 100)
        self.TimeProgress = int((self.Time / self.MaxTime) * 100)

        self.StepDelta = self.Step - self.PreviousStep
        # TimeDelta is provided externally
        self.RealTimeDelta = self.CurrentRealTime - self.PreviousRealTime

        if self.RealTimeDelta > 0:
            self.StepSpeed = self.StepDelta / self.RealTimeDelta
            self.TimeSpeed = self.TimeDelta / self.RealTimeDelta

        self.StepETA = self.LeftSteps / self.StepSpeed
        self.TimeETA = self.LeftTime / self.TimeSpeed

        self.ElapsedRealTimeEfficiency = int((self.ElapsedInternalRealTime /  self.ElapsedRealTime) * 100)
        self.RealTimeDeltaEfficiency = int((self.InternalRealTimeDelta / self.RealTimeDelta) * 100)

        self.PreviousStep = self.Step
        self.PreviousRealTime = self.CurrentRealTime

        self.Updated = True

class RuntimeStats:
    Loop = 0
    DataSize = 0
    PreviousLoop = 0
    PreviousDataSize = 0

    LoopDelta = 0
    DataDelta = 0

    CurrentTime = 0
    PreviousTime = 0

    LoopSpeed = 0
    DataSpeed = 0

    def Recalculate(self):
        self.CurrentTime = time.time()

        self.Delta = self.CurrentTime - self.PreviousTime
        self.LoopDelta = self.Loop - self.PreviousLoop
        self.DataDelta = self.DataSize - self.PreviousDataSize

        self.LoopSpeed = self.LoopDelta / self.Delta
        self.DataSpeed = self.DataDelta / self.Delta

        self.PreviousTime = self.CurrentTime
        self.PreviousLoop = self.Loop
        self.PreviousDataSize = self.DataSize
        #print(self.DataSpeed, self.DataDelta, self.Delta)

class UI:
    class Section(enum.Enum):
        WAIT = 0
        HEADER = 1
        MAIN = 2
        FOOTER = 3

    NonDestructive = False
    Stats = None
    UpdateTimer = None
    MinLen = 0
    MaxLen = 0
    CurrentSection = Section.WAIT

    SimStatsHeight = 7
    RtStatsHeight = 3
    MessageLineHeight = 1

    def __init__(self, SimStats, RtStats, Interval):
        self.Terminal = Terminal()
        print(self.Terminal.clear_bol)
        self.First = True
        self.SimStats = SimStats
        self.RtStats = RtStats
        self.UpdateTimer = Timer(Interval)
        self.MsgLine = MessageLine(Timeout = 2, FillWith = "-", LineLen = 77)

    def IsDestructive(self):
        d = self.NonDestructive
        if d == None:
            d = self.__class__.NonDestructive
        return d

    def GetMinLen(self, Length = None):
        if Length == None:
            Length = self.MinLen
            if Length == None:
                Length = self.__class__.MinLen
        return Length

    def CacheMaxLen(self, MaxLen = None):
        if MaxLen == None:
            self.MaxLen = shutil.get_terminal_size().columns
        else:
            self.MaxLen = MaxLen

    def GetMaxLen(self, MaxLen = None):
        if MaxLen == None:
            return self.MaxLen
        return self.MaxLen

    def GetLen(self, Min = None, Max = None):
        Min = self.GetMinLen(Min)
        Max = self.GetMaxLen(Max)
        return min(Min, Max), Max

    def PrintLine(self, Text, End = "\n"):
        print(Text + self.Terminal.clear_eol, end = End)

    def WriteHeader(self):
        lmin, lmax = self.GetLen()
#        print(lmin, lmax, Length)
        d = self.IsDestructive()
        self.PrintLine("+" + "-" * (lmin - 2) + "+")
        fmt = f"|{{:^{lmin - 2}}}|"
        self.PrintLine(fmt.format("Time statistics:"))
        self.PrintLine("+" + "-" * (lmin - 2) + "+")
        End = '\n\n\n\n\n'
        if self.NonDestructive:
            End = "\n"
        print("|", end=End)

    def WriteSimStats(self):
        s = self.SimStats # Less to write
        minl, maxl = self.GetLen()
        s1 = f"|   Step:  {FmtNmb.Str(s.Step):^15} / {FmtNmb.Str(s.MaxSteps):^15} : {FmtNmb.Str(s.LeftSteps):^15} ({FmtNmb.Str(s.StepsProgress):>3}%), x{FmtNmb.Str(s.StepSpeed):>11}, ETA: {FmtTime.Str(s.StepETA):>20}"

        s2 = f"|   Sim time: {FmtTime.Str(s.Time):^10}   /    {FmtTime.Str(s.MaxTime):^10}   :   {FmtTime.Str(s.LeftTime):^10}    ({FmtNmb.Str(s.TimeProgress):>3}%), x{FmtNmb.Str(s.TimeSpeed):>11}, ETA: {FmtTime.Str(s.TimeETA):>20}"

        s3 = f"|   Elapsed: {FmtTime.Str(s.ElapsedRealTime)}, delta: {FmtTime.Str(s.RealTimeDelta)} ({FmtTime.Str(s.TimeDelta * s.StepDelta)}), eff: elapsed: {s.ElapsedRealTimeEfficiency}%, delta: {s.RealTimeDeltaEfficiency}%"

#        if not self.NonDestructive:
#            print('\r\033[A\033[A\033[A\033[A\033[A', end='')
        self.PrintLine(s1)
        self.PrintLine(s2)
        self.PrintLine(s3)
        self.PrintLine("|")
        s.Updated = False

    def WriteRtStats(self):
        s = self.RtStats
        minl, maxl = self.GetLen()
        self.PrintLine("+" + "-" * (minl - 2) + "+")
        self.PrintLine(f"|   Proc. data: {SizeStr(s.DataSize):>10}, {SizeStr(s.DataSpeed):>10}/s")


    def WriteMessageLine(self):
        minl, maxl = self.GetLen()
        self.PrintLine(f"+{self.MsgLine.GetLine(LineLen = minl - 2)}+")

    def Rewrite(self, Force):
#        print("+", end = '')
#        sys.stdout.flush()
        #return
        self.CacheMaxLen()
        with self.Terminal.no_line_wrap():
            if self.SimStats.Updated or Force:
                MoveUp = self.SimStatsHeight
            else:
                MoveUp = self.RtStatsHeight
            if MoveUp and not self.NonDestructive:
#            print(f"Move up by: {MoveUp}")
                print(self.Terminal.move_up(MoveUp + 1))
            if self.First:
                self.WriteHeader()
                self.First = False
            if self.SimStats.Updated or Force:
                self.WriteSimStats()
            self.WriteRtStats()
            self.WriteMessageLine()

    def Update(self, Force = False):
#        print(".", end = '')
        if self.UpdateTimer.Expired() or Force:
            if self.CurrentSection == self.Section.MAIN:
                self.RtStats.Recalculate()
                if not Config.Quiet:
                    self.Rewrite(Force)
            self.UpdateTimer.Reset()

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

SimStats = SimulationStats(Config.MaxSteps, Config.MaxTime)
RtStats = RuntimeStats()
MainUI = UI(SimStats, RtStats, Config.UpdateInterval)
MainUI.NonDestructive = Config.NonDestructivePrint
MainUI.MinLen = 79
MainTimer = Timer(Config.UpdateInterval)

ControlInput = InputTerminal(MainUI.Terminal, EventQueue)
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

        RtStats.Loop += 1
        MainUI.Update()

        while not EventQueue.empty():
            EventQueue.get_nowait() # eat stalled events

        while 1:
            key = ControlInput.Read()
            if key == None:
                break
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
                MainUI.MsgLine.SetTemporary(msg)
            elif CompareKeys(key, Config.NDestPrintKey):
                MainUI.NonDestructive = not MainUI.NonDestructive
            elif CompareKeys(key, Config.PauseKey):
                if Paused:
                    if WarpxProcess != None:
                        Processes.ResumeTree(WarpxProcess)
                    Paused = False
                    MainUI.MsgLine.SetPersistent()
                    MainUI.MsgLine.SetTemporary("Resumed")
                else:
                    if WarpxProcess != None:
                        Processes.PauseTree(WarpxProcess)
                    Paused = True
                    MainUI.MsgLine.SetPersistent("Paused")
            else:
                MainUI.MsgLine.SetTemporary(key)
            MainUI.Update(True)
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
                MainUI.PrintLine(f"{Start}   Waiting for WarpX to start sending data for: {FmtTime.Str(WaitingFor)}", End)

        #if not (Header or Footer):
        #    MainUI.Update()

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

        RtStats.DataSize += len(OutputLine)

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
            MainUI.CurrentSection = UI.Section.HEADER
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

            SimStats.Step = int(nums[0])
            SimStats.Time = float(nums[1])
            SimStats.TimeDelta = float(nums[2])

            SimStats.Recalculate(time.time())

            MainUI.Update(True)

            MainUpdated = True

        elif not SecondUpdated and Re2.search(OutputLine):
            nums = ReNum.findall(OutputLine)
        #print(nums)

            SimStats.ElapsedInternalRealTime = float(nums[0])
            SimStats.InternalRealTimeDelta = float(nums[1])
            SecondUpdated = True

        elif Header == True and ReHead.match(OutputLine):
            MainUI.CurrentSection = UI.Section.MAIN
            Header = False

        elif Footer == False and ReFoot.match(OutputLine):
            Footer = True
            MainUI.CurrentSection = UI.Section.FOOTER
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

MainUI.CurrentSection = UI.Section.FOOTER

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
