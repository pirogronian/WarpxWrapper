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

from FormattedValue import FormattedNumber, FormattedTime
from NonBlockingInput import NonBlockingInput
from NonBlockingPipe import NonBlockingPipe

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

DefaultWarpxInputFile = "input"
ExecBase = "warpx."
ExecDim = "3d"
Executable = ""
Command = ""

UseMpi = False

InputFile = ""
SkipMain = False
SkipFooter = False
DontWaitForFooter = True
NonDestructivePrint = False

Params = []

BreakKey = "\x1b"
ISOKey = "f"
NDestPrintKey = "d"

def CompareChars(c1, c2):
    if type(c1) == type(c2):
        return c1 == c2
    if type(c1) == str:
        return ord(c1) == c2
    return c1 == ord(c2)

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
    if level >= LogLevel:
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
AddParam("UpdateInterval", "--upd-int", "--update-interval")
AddParam("MaxSteps", "-x", "--max-steps")
AddParam("MaxTime", "-t", "--max-time")
AddParam("SkipMain", "-a", "--skip-main-loop", const = True)
AddParam("SkipFooter", "-f", "--skip-footer", const = True)
AddParam("DontWaitForFooter", "--dont-wait-for-footer", const = True)
AddParam("Source", "-s", "--source", action=SourceAction, choices=Sources.keys())
AddParam("InputFile","-i", "--input-file")
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

#InputData = None
#IsFifo = False

InputPipe = NonBlockingPipe()

def PrepareStdin():
#    global InputData
#    global IsFifo
#    InputData = sys.stdin
#    IsFifo = True
    global InputPipe
    InputPipe.Input = sys.stdin

def PrepareInputFile():
#    global InputData
#    global IsFifo
    global InputPipe
    LogDebug(f"Opening WarpX output file: '{InputFile}'")
    try:
        InputData = open(InputFile, "r")
    except Exception as e:
        LogWarning(f"Cannot open data file '{InputFile}' for reading, trying to create it...")
        LogWarning(1, e)
        try:
            open(InputFile, "x")
        except Exception as e:
            LogCritical(f"Cannot open nor create data file '{InputFile}'.")
            Fatal(1, e)
        try:
            InputData = open(InputFile, "r")
        except Exception as e:
            LogCritical("Cannot open created data file '{InputFile}'.")
            Fatal(1, e)
    InputPipe.Input = InputData
    LogDebug("File '{InputFile}' successfully opened.")
    if not pathlib.Path(InputFile).is_fifo():
        LogDebug(f"'{InputFile}' is not a fifo, don't exit on empty read.")
        InputPipe.ExitOnEmpty = False
        InputPipe.Interval = UpdateInterval

WarpxProcess = None

def PrepareCommand():
    global Command
    global InputFile
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
        if InputFile == "":
            InputFile = DefaultWarpxInputFile
        if not IsReadable(InputFile):
            Error(f"Warpx input file \"{InputFile}\" is not readable.")

        CmdArgs.append(InputFile)

    RunMsg = f"|   Running WarpX 3D with the following command: {CmdArgs}   |"
    RunMsgLen = len(RunMsg)

    Panel = "-" * RunMsgLen
    LogDebug(Panel)
    LogDebug(RunMsg)
    LogDebug(Panel)

    try:
        WarpxProcess = subprocess.Popen(args=CmdArgs,stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    except Exception as e:
        LogCritical("Cannot create a subprocess to get its output.")
        Fatal(1, e)

    InputPipe.Input = WarpxProcess.stdout

PrintParams()

MsgEnd = ''
if NonDestructivePrint:
    MsgEnd = '\n'

if Source == SourceType.STDIN:
    PrepareStdin()
elif Source == SourceType.FILE:
    PrepareInputFile()
else:
    PrepareCommand()

PrepareLogging()

FmtNmb = FormattedNumber()
FmtTime = FormattedTime()
FmtNmb.ForbidNegative = True

CurrentTime = 0
PreviousTime = 0
StartTime = -1

PureElapsed = 0
PureDelta = 0

Header = True
Footer = False
SkipMain = False

MainUpdated = False
SecondUpdated = False
LastUpdated = 0

MeanStepETA = 0
MeanTimeETA = 0
Steps = 0

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

IInput = NonBlockingInput()
if Source == SourceType.STDIN: # Sorry, not interactive mode (or use another i/o stream)
    IInput.IOStream = None
IInput.DisableBlocking()

LogDebug("Activating input non-blocking pipe.")
InputPipe.Activate()
LogDebug(1, f"Pipe activity status: {InputPipe.IsActive()}.")

while 1:
    if SkipMain:
        LogDebug("Skipping main.")
        break

    char = IInput.ReadLastChar()
    if char != None:
        if CompareChars(char, BreakKey):
            LogInfo("Breaking on user demand.")
            break
        if CompareChars(char, ISOKey):
            FmtTime.ISO = not FmtTime.ISO
        elif CompareChars(char, NDestPrintKey):
            NonDestructivePrint = not NonDestructivePrint

    if StartTime < 0:
        WaitingFor = time.time() - WaitForDataStart
        if WaitingFor > 0:
            msg = f"   Waiting for WarpX to start sending data for: {FmtTime.Str(WaitingFor)}"
            if not NonDestructivePrint:
                msg = '\r' + msg
            print(msg, end=MsgEnd)

    OutputLine = InputPipe.Read()
    if OutputLine == None:
        #print("Read null string")
        if (InputPipe.IsActive()):
#            print("InputPipe active, waiting.")
            time.sleep(UpdateInterval)
            continue # So all interactivity must take place earlier
        else:
            LogDebug("InputPipe inactive, finishing.")
            break

    if StartTime < 0:
        StartTime = time.time()
        print("\n   Got data, starting processing.\n")

        if LogWritable:
            try:
                LogStream.write(OutputLine)
            except Exception as e:
                warning("An error while writing to log file.")
                warning(1, e)


    if MainUpdated and SecondUpdated:
        CurrentTime = time.time()
        if CurrentTime - LastUpdated > UpdateInterval:
            LastUpdated = CurrentTime
            MainUpdated = False
            SecondUpdated = False


    if not Footer and not MainUpdated and Re1.search(OutputLine):
        nums = ReNum.findall(OutputLine)
        Step = int(nums[0])
        SimulationElapsed = float(nums[1])
        SimulationDelta = float(nums[2])
        #print(nums)
        #print(Step, SimulationElapsed, SimulationDelta)
        #print(OutputLine)

        CurrentTime = time.time()
        Elapsed = CurrentTime-StartTime
        Delta = CurrentTime-PreviousTime
        RemainingSteps = -1
        StepsProgress = -1
        StepsETA = -1
        if MaxSteps > 0:
            RemainingSteps = MaxSteps-Step
            StepsProgress = int(Step/MaxSteps*100)
            StepsETA = Delta*RemainingSteps
            MeanStepETA += StepsETA

        RemainingSimTime = -1
        TimeProgress = -1
        TimeETA = -1
        if MaxTime > 0:
            RemainingSimTime = MaxTime-SimulationElapsed
            TimeProgress = int(SimulationElapsed/MaxTime*100)
            RealToSimTime = Delta/SimulationDelta
            TimeETA = RealToSimTime*RemainingSimTime
            MeanTimeETA += TimeETA

        Steps = Step

        EffElapsed = int(PureElapsed/Elapsed*100)
        EffDelta = int(PureDelta/Delta*100)

        StepsMsg = f"|   Step:  {FmtNmb.Str(Step):^15} / {FmtNmb.Str(MaxSteps):^15} : {FmtNmb.Str(RemainingSteps):^15} ({FmtNmb.Str(StepsProgress):>3}%), ETA: {FmtTime.Str(StepsETA):>20}           "

        TimeMsg = f"|   Sim time: {FmtTime.Str(SimulationElapsed):^10}   /    {FmtTime.Str(MaxTime):^10}   :   {FmtTime.Str(RemainingSimTime):^10}    ({FmtNmb.Str(TimeProgress):>3}%), ETA: {FmtTime.Str(TimeETA):>20}          "

        Time2Msg = f"|   Elapsed: {FmtTime.Str(Elapsed)}, delta: {FmtTime.Str(Delta)} ({FmtTime.Str(SimulationDelta)}), eff: elapsed: {EffElapsed}%, delta: {EffDelta}%          "

        if not NonDestructivePrint:
            print('\r\033[A\033[A\033[A\033[A\033[A', end='')
        print(StepsMsg,)
        print(TimeMsg,)
        print(Time2Msg)
        print("|")
        print("+-----------------------------------------------------------------------------+")

        PreviousTime = CurrentTime
        MainUpdated = True

    elif not SecondUpdated and Re2.search(OutputLine):
        nums = ReNum.findall(OutputLine)
        #print(nums)

        PureElapsed = float(nums[0])
        PureDelta = float(nums[1])
        SecondUpdated = True

    elif Header == True and ReHead.match(OutputLine):
        print("+-----------------------------------------------------------------------------+")
        print("|                            Time statistics:                                 |")
        print("+-----------------------------------------------------------------------------+")
        End = '\n\n\n\n\n\n'
        if NonDestructivePrint:
            End = "\n"
        print("|", end=End)
        Header = False

    elif Footer == False and ReFoot.match(OutputLine):
        Footer = True
        LogDebug("Footer detected.")
        if SkipFooter:
            break
        time.sleep(UpdateInterval) # Let some time to the pipe to read last of data.
        InputPipe.ExitOnEmpty = true # Don't wait for data anymore.
    elif ReAbort.match(OutputLine):
        LogWarning("Warpx aborted.")
        break

    if Header or Footer:
        print(OutputLine, end='')

    if MainUpdated and SecondUpdated:
        CurrentTime = time.time()
        if CurrentTime - LastUpdated > UpdateInterval:
            LastUpdated = CurrentTime
            MainUpdated = False
            SecondUpdated = False


IInput.RestoreBlocking()

"""print(MeanStepETA, MeanTimeETA, MeanTest, Steps)

MeanStepETA /= Steps
MeanTimeETA /= Steps
MeanTest /= Steps

print(MeanStepETA, MeanTimeETA, MeanTest)"""

FMsg = "Finished in " + FmtTime.Str(CurrentTime-StartTime)
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
