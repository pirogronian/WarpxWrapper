#!/usr/bin/python -u

import sys
import os
import subprocess
import regex
import time
import datetime
import logging
import pathlib
import enum
import argparse
import signal
import shutil
from blessed import Terminal
from queue import Queue

from FormattedValue import FormattedNumber, FormattedTime
from NonBlockingStream import TextInputStream, InputTerminal
from FileWatcher import FileWatcher
import FitLine
from MessageLine import MessageLine
from Timer import Timer
from Various import CompareKeys

class Verbosity(enum.Enum):
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL

LogLevel = Verbosity.INFO

ErrorIsFatal = True

UpdateInterval = 0.5

DontRun = False

MaxSteps = -1
MaxTime = -1.0

LogFile = "Log.txt"

class SourceType(enum.Enum):
    DEFAULT = 0 # It means the COMMAND
    COMMAND = 1
    FILE    = 2
    STDIN   = 3

Source = SourceType.DEFAULT

DefaultWarpxInputFileName = "input"
ExecBase = "warpx."
ExecDim = "3d"
Executable = ""
Command = ""

UseMpi = False

InputFileName = ""

PID = 0
AbortOnExit = False

SkipMain = False
SkipFooter = False
DontWaitForFooter = True
NonDestructivePrint = False

Params = []

BreakKey = 27
ISOKey = "f"
NDestPrintKey = "d"
PauseKey = ' '

class ColorfulFormatter(logging.Formatter):

    grey = "\x1b[38;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    format = "%(levelname)s - %(message)s"

    FORMATS = {
        logging.DEBUG: grey + format + reset,
        logging.INFO: grey + format + reset,
        logging.WARNING: yellow + format + reset,
        logging.ERROR: red + format + reset,
        logging.CRITICAL: bold_red + format + reset
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)

logger = logging.getLogger("WarpxWrapper")
logHandler = logging.StreamHandler()
logFormatter = ColorfulFormatter()
logHandler.setFormatter(logFormatter)
logger.addHandler(logHandler)
logger.setLevel(logging.DEBUG)

def prepareLog(*arg):
    args = list(arg)
    nest = 0
    prefix = ""
#    prefix += "   "
    if len(args) > 1:
        nest = args[0]
    if isinstance(nest, int) and nest > 0:
        prefix = "   " * nest
        args.pop(0)

    msg = "".join(str(item) for item in args)
    msg = prefix + msg

    return msg

def Log(level, *args):
    if logger.level != LogLevel: # Let user for simple LogLevel = <level> to work
        logger.setLevel(LogLevel.value)
    msg = prepareLog(*args)
    logger.log(level.value, msg)

def LogDebug(*args):
    Log(Verbosity.DEBUG, *args)

def LogInfo(*args):
    Log(Verbosity.INFO, *args)

def LogWarning(*args):
    Log(Verbosity.WARNING, *args)

def LogError(*args):
    Log(Verbosity.ERROR, *args)

def LogCritical(*args):
    Log(Verbosity.CRITICAL, *args)

def LogExcept(level, *args):
#    print(level, LogLevel)
    if level.value >= LogLevel.value:
        msg = prepareLog(args)
        logger.exception(msg)

def LogExceptDebug(*args):
    LogExcept(Verbosity.DEBUG, *args)

def LogExceptInfo(*args):
    LogExcept(Verbosity.INFO, *args)

def LogExceptWarn(*args):
    LogExcept(Verbosity.WARNING, *args)

def LogExceptCrit(*args):
    LogExcept(Verbosity.CRITICAL, *args)

def LogExceptError(*args):
    LogExcept(Verbosity.ERROR, *args)

def Error(*args):
    if args:
        LogError(*args)
    if ErrorIsFatal:
        LogError(" ^^^^ An error occured, aborting. ^^^^")
        exit(1)

def Fatal(*args):
    if args:
        LogCritical(*args)
        LogCritical(" ^^^^ An error occured, aborting. ^^^^")
        exit(1)

def IsReadable(fname):
    return os.access(fname, os.R_OK)

def IsWritable(fname):
    return os.access(fname, os.W_OK)

def IncludeFile(fname):
    LogDebug("Including file '{}'.".format(fname))
    try:
        f = open(fname, "r")
    except Exception as e:
        LogError("Cannot open file '{}'.".format(fname))
        Error(1, e)
        return
    prog = f.read()
    try:
        exec(prog, globals())
    except Exception as e:
        LogError("Error while executing include file: '{}'".format(fname))
        LogExceptError(1, e)
        Error()

def PrintParam(name):
    Globals = globals()
    Value = Globals[name]
    TypeName = type(Value).__name__
    LogDebug(1, "{} = {} ({})".format(name, Value, TypeName))

def PrintParams():
    LogDebug("Printing current configuration:")
    for name in Params:
        PrintParam(name)

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
        global LogLevel
        LogLevel = LogLevels[value]
        LogDebug("Command line: set LogLevel to '{}'.".format(value))
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
        Source = Sources[key]
        LogDebug("Command line: set Source to {}".format(key))
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
        value = values
        t = type(globals()[self.Param])
        if self.UnpackList and type(value) == list:
            value = value[0]
        try:
            value = StrToType(value, t)
        except:
            Error("Value of param {} must be convertable to {}!".format(option_string, t.__name__))
        globals()[self.Param] = value
        LogDebug("Command line: set {} to {}".format(self.Param, value))

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
    if VarName in globals():
        global parser
        if not "nargs" in KArgs:
            KArgs["nargs"] = '?' if "const" in KArgs else 1
        if not "action" in KArgs:
            KArgs["action"] = ParamAction
        if not "help" in KArgs:
            KArgs["help"] = "Type: {}.".format(TypeDescription(type(globals()[VarName]), True))
        parser.add_argument(*Args, VarName = VarName, **KArgs)
        Params.append(VarName)
    else:
        raise NameError("Variable {} not found.".format(VarName))

AddParam("LogLevel", "-v", "--verbosity", action=VerbosityAction, const='debug', choices=LogLevels.keys())
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
AddParam("InputFileName","-i", "--input-file")
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
    LogDebug(f"Cannot read default config file: '{DefaultConfigFile}'")

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
    if LogFile != "":
        try:
            LogStream = open(LogFile, "w")
            LogWritable = True
        except Exception as e:
            LogError(f"An exception occured while opening the log file '{LogFile}':")
            Error(1, e)
            LogWritable = False

#DataStream = None
#IsFifo = False

DataInput = TextInputStream()

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
    LogDebug(f"Opening WarpX output file: '{InputFileName}'")
    try:
        DataStream = open(InputFileName, "r")
    except Exception as e:
        LogWarning(f"Cannot open data file '{InputFileName}' for reading, trying to create it...")
        LogWarning(1, e)
        try:
            open(InputFileName, "x")
        except Exception as e:
            LogCritical(f"Cannot open nor create data file '{InputFileName}'.")
            Fatal(1, e)
        try:
            DataStream = open(InputFileName, "r")
        except Exception as e:
            LogCritical(f"Cannot open created data file '{InputFileName}'.")
            Fatal(1, e)
    DataInput.Stream = DataStream
    LogDebug(f"File '{InputFileName}' successfully opened.")
    if not pathlib.Path(InputFileName).is_fifo():
        LogDebug(f"'{InputFileName}' is not a fifo, don't exit on empty read.")
        DataInput.Interval = UpdateInterval

WarpxProcess = None

def PrepareCommand():
    global Command
    global InputFileName
    global WarpxProcess

    CmdArgs = []

    if UseMpi:
        CmdArgs.append("mpirun")

    if type(Command) == str and Command != "":
        CmdArgs.extend(Command.split())
    elif type(Command) == list and len(Command) > 0:
        for arg in Command:
            subargs = arg.split()
            CmdArgs.extend(subargs)
    else:
        if Executable != "":
            CmdArgs.append(Executable)
        else:
            CmdArgs.append(ExecBase + ExecDim)

    if Command == "":
        if InputFileName == "":
            InputFileName = DefaultWarpxInputFileName
        if not IsReadable(InputFileName):
            Error(f"Warpx input file \"{InputFileName}\" is not readable.")

        CmdArgs.append(InputFileName)

    RunMsg = f"|   Running WarpX 3D with the following command: {CmdArgs}   |"
    RunMsgLen = len(RunMsg)

    Panel = "-" * RunMsgLen
    LogDebug(Panel)
    LogDebug(RunMsg)
    LogDebug(Panel)

    try:
        WarpxProcess = subprocess.Popen(args=CmdArgs,
                                        stdin=subprocess.DEVNULL,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT,
                                        text=True)
    except Exception as e:
        LogCritical("Cannot create a subprocess to get its output.")
        Fatal(1, e)

    DataInput.Stream = WarpxProcess.stdout

PrintParams()

if Source == SourceType.STDIN:
    PrepareStdin()
elif Source == SourceType.FILE:
    PrepareInputFileName()
else:
    PrepareCommand()

PrepareLogging()

FmtNmb = FormattedNumber()
FmtTime = FormattedTime()
FmtNmb.ForbidNegative = True

StartTime = -1

class Stats:
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

    def __init__(self, Stats, Interval):
        self.Terminal = Terminal()
        print(self.Terminal.clear_bol)
        self.First = True
        self.Stats = Stats
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
        d = self.IsDestructive()
        Max = self.GetMaxLen()
        if not d:
            Text = FitLine.FitLeft(Text, Max)
        print(Text, end = End)

    def WriteHeader(self, Length):
        lmin, lmax = self.GetLen()
        d = self.IsDestructive()
        self.PrintLine("+" + "-" * (lmin - 2) + "+")
        fmt = f"|{{:^{lmin - 2}}}|"
        self.PrintLine(fmt.format("Time statistics:"))
        self.PrintLine("+" + "-" * (lmin - 2) + "+")
        End = '\n\n\n\n\n\n'
        if self.NonDestructive:
            End = "\n"
        print("|", end=End)

    def WriteStats(self, Length):
        s = self.Stats # Less to write
        minl, maxl = self.GetLen()
        s1 = f"|   Step:  {FmtNmb.Str(s.Step):^15} / {FmtNmb.Str(s.MaxSteps):^15} : {FmtNmb.Str(s.LeftSteps):^15} ({FmtNmb.Str(s.StepsProgress):>3}%), x{FmtNmb.Str(s.StepSpeed):>11}, ETA: {FmtTime.Str(s.StepETA):>20}"

        s2 = f"|   Sim time: {FmtTime.Str(s.Time):^10}   /    {FmtTime.Str(s.MaxTime):^10}   :   {FmtTime.Str(s.LeftTime):^10}    ({FmtNmb.Str(s.TimeProgress):>3}%), x{FmtNmb.Str(s.TimeSpeed):>11}, ETA: {FmtTime.Str(s.TimeETA):>20}"

        s3 = f"|   Elapsed: {FmtTime.Str(s.ElapsedRealTime)}, delta: {FmtTime.Str(s.RealTimeDelta)} ({FmtTime.Str(s.TimeDelta * s.StepDelta)}), eff: elapsed: {s.ElapsedRealTimeEfficiency}%, delta: {s.RealTimeDeltaEfficiency}%"

        if not self.NonDestructive:
            print('\r\033[A\033[A\033[A\033[A\033[A', end='')
        self.PrintLine(s1)
        self.PrintLine(s2)
        self.PrintLine(s3)
        self.PrintLine("|")
        self.PrintLine(f"+{self.MsgLine.GetLine(LineLen = minl - 2)}+")

    def Rewrite(self, Length = None):
#        print("+", end = '')
#        sys.stdout.flush()
        #return
        if self.First:
            self.WriteHeader(Length)
            self.First = False
        self.WriteStats(Length)

    def Update(self):
#        print(".", end = '')
        if self.UpdateTimer.Expired():
            self.CacheMaxLen()
            if self.CurrentSection == self.Section.MAIN:
                self.Rewrite()
            self.UpdateTimer.Reset()

Header = True
Footer = False
SkipMain = False

MainUpdated = False
SecondUpdated = False

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
LogDebug("\n      Start waiting for WarpX Data...\n")

if DontRun:
    exit(0)

EventQueue = Queue()

MainStats = Stats(MaxSteps, MaxTime)
MainUI = UI(MainStats, UpdateInterval)
MainUI.NonDestructive = NonDestructivePrint
MainUI.MinLen = 79
MainTimer = Timer(UpdateInterval)

ControlInput = InputTerminal(MainUI.Terminal, EventQueue)
if Source == SourceType.STDIN: # Sorry, not interactive mode (or use another i/o stream)
    ControlInput.Source = None

DataInput.EventQueue = EventQueue
DataInput.Event = False
DataInput.QueueSizeThreshold = 100

LogDebug("Activating input non-blocking pipe.")
DataInput.Activate()
LogDebug(1, f"Pipe activity status: {DataInput.IsActive()}.")

if ControlInput.Stream != None:
    LogDebug("Activating stdin non-blocking pipe.")
    ControlInput.Activate()
    LogDebug(1, f"Pipe activity status: {ControlInput.IsActive()}.")

FWatcher = FileWatcher(InputFileName)
ExcludePids = []

print("\n")

Finishing = False

try:
    ControlInput.DisableBuffering()

    while 1:
        if SkipMain:
            LogDebug("Skipping main.")
            break

        while 1:
            key = ControlInput.Read()
            if key == None:
                break
            print("Keys: ", key)
            if CompareKeys(key, BreakKey):
                print("\n\n")
                LogInfo(f"Breaking on user demand.")
                Finishing = True
                break
            if CompareKeys(key, ISOKey):
                FmtTime.ISO = not FmtTime.ISO
                msg = "ISO "
                if FmtTime.ISO:
                    msg += "set"
                else:
                    msg += "unset"
                MainUI.MsgLine.SetTemporary(msg)
            elif CompareKeys(key, NDestPrintKey):
                NonDestructivePrint = not NonDestructivePrint
                MainUI.NonDestructive = not MainUI.NonDestructive
            elif CompareKeys(key, PauseKey):
                Sig = -1
                if Paused:
                    Sig = signal.SIGCONT
                    Paused = False
                    MainUI.MsgLine.SetPersistent()
                    MainUI.MsgLine.SetTemporary("Resumed")
                else:
                    Sig = signal.SIGSTOP
                    Paused = True
                    MainUI.MsgLine.SetPersistent("Paused")
                if WarpxProcess != None:
                    WarpxProcess.send_signal(Sig)
                elif PID > 0:
                    os.kill(PID, Sig)
            else:
                MainUI.MsgLine.SetTemporary(key)
            MainUI.Rewrite()
        if Finishing:
            break

        if StartTime < 0:
            WaitingFor = time.time() - WaitForDataStart
            if WaitingFor > 0:
                End = ''
                Start = ''
                if NonDestructivePrint:
                    End = '\n'
                else:
                    Start = '\r'
                MainUI.PrintLine(f"{Start}   Waiting for WarpX to start sending data for: {FmtTime.Str(WaitingFor)}", End)

        Pids = []
        if PID == 0 and Source == SourceType.FILE:
            Pids = FWatcher.DetectPids(Exclude = ExcludePids)

        MainUI.Update()

        OutputLine = DataInput.Read()
        if OutputLine == None:
            #print("Read null string")
            if (DataInput.IsActive()):
                ExcludePids = Pids # Detected processes are not our writer
                #print(f"DataInput active, waiting for {UpdateInterval}.")
                try:
                    EventQueue.get(timeout=UpdateInterval)
                except Exception as e:
                    #LogDebug("Exception while waiting for event.")
                    #LogExceptDebug(e)
                    pass
                continue # So all interactivity must take place earlier
            else:
                LogDebug("DataInput inactive, finishing.")
                break

        if PID == 0 and Source == SourceType.FILE:
            if ExcludePids == []: # Probably the first process is the writer
                ExcludePids.append(os.getpid())
                PID = FWatcher.DetectFirstPid(Exclude = ExcludePids)
            else:
                PID = FWatcher.DetectLastPid(Exclude = ExcludePids)
            if PID == None:
                if OutputLine == None:
                    PID = 0
                else: # File has data, clearly is already written.
                    PID = -1
            LogDebug(f"\nDetected PID: {PID} (excluded: {ExcludePids}).")


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

            MainStats.Step = int(nums[0])
            MainStats.Time = float(nums[1])
            MainStats.TimeDelta = float(nums[2])

            MainStats.Recalculate(time.time())

            MainUI.Rewrite()

            MainUpdated = True

        elif not SecondUpdated and Re2.search(OutputLine):
            nums = ReNum.findall(OutputLine)
        #print(nums)

            MainStats.ElapsedInternalRealTime = float(nums[0])
            MainStats.InternalRealTimeDelta = float(nums[1])
            SecondUpdated = True

        elif Header == True and ReHead.match(OutputLine):
            MainUI.CurrentSection = UI.Section.MAIN
            Header = False

        elif Footer == False and ReFoot.match(OutputLine):
            Footer = True
            MainUI.CurrentSection = UI.Section.FOOTER
            LogDebug("Footer detected.")
            if SkipFooter:
                break
            time.sleep(UpdateInterval) # Let some time to the pipe to read last of data.
            DataInput.Interval = 0 # Don't wait for data anymore.
        elif ReAbort.match(OutputLine):
            LogWarning("Warpx aborted.")
            break

        if Header or Footer:
            print(OutputLine, end='')

        if MainUpdated and SecondUpdated:
            if MainTimer.Expired():
                MainTimer.Reset()
                MainUpdated = False
                SecondUpdated = False

except Exception as e:
    LogCritical("Unhandled exception, restoring terminal settings.")
    ControlInput.RestoreBuffering()
    LogExceptCrit(e)
    exit(1)

ControlInput.RestoreBuffering()

MainUI.CurrentSection = UI.Section.FOOTER

"""print(MeanStepETA, MeanTimeETA, MeanTest, Steps)

MeanStepETA /= Steps
MeanTimeETA /= Steps
MeanTest /= Steps

print(MeanStepETA, MeanTimeETA, MeanTest)"""

if AbortOnExit and PID > 0:
    os.kill(PID, signal.SIGABRT)

FMsg = "Finished in " + FmtTime.Str(time.time() - StartTime)
FMsg = "|{:^77}|".format(FMsg)

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
