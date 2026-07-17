
import sys
import os
import subprocess
import regex
import time
import datetime
import configparser
import logging
import pathlib

WarpxInputFile = "input"
ExecBase = "warpx."
ExecDim = "3d"
FullCommand = ""

TotalSimSteps = -1
TotalSimTime = -1

UpdateInterval = 0.5

UseMpi = False

LogFile = "Log.txt"

WarpxOutputFile = "output.txt"
UseWarpxOutputFile = False
IsFifo = False
WaitForStart = False
WaitForData = False
SkipFooter = False
DontWaitForFooter = True

UseStdin = False

LogLevels = {
        'debug': logging.DEBUG,
        'info': logging.INFO,
        'warning': logging.WARNING,
        'error' : logging.ERROR,
        'critical' : logging.CRITICAL
    }

logger = logging.getLogger("WarpxWrapper")
logHandler = logging.StreamHandler()
logFormatter = logging.Formatter("%(levelname)s:  %(message)s")
logHandler.setFormatter(logFormatter)
logger.addHandler(logHandler)
logger.setLevel(logging.DEBUG)

def prepareLog(arg):
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

def debug(*args):
    msg = prepareLog(args)
    logger.debug(msg)

def info(*args):
    msg = prepareLog(args)
    logger.info(msg)

def warning(*args):
    msg = prepareLog(args)
    logger.warning(msg)

def error(*args):
    msg = prepareLog(args)
    logger.error(msg)

def critical(*args):
    msg = prepareLog(args)
    logger.critical(msg)

def exception(*args):
    msg = prepareLog(args)
    logger.exception(msg)

DefaultConfigFileName = "config.ini"

ConfigFileName = ""
if len(sys.argv) > 1:
    ConfigFileName = sys.argv[1]

if not ConfigFileName:
    debug("No config file provided, falling back to default: " + DefaultConfigFileName)
    ConfigFileName = DefaultConfigFileName

config = configparser.ConfigParser(allow_unnamed_section=True, allow_no_value=True)
config.optionxform = str
config.read(ConfigFileName)

def getCfgCommon(name, option, default=None, section=configparser.UNNAMED_SECTION):
    method = getattr(config, name)
    try:
        val = method(section, option, fallback=default)
        debug("Config: {}.{} = {}".format(section, option, val))
    except Exception as e:
        warning("Warning, exception while reading config option \'{}\':".format(option))
        warning(1, e)
        val = default
    return val

def getCfgBool(option, default=None, section=configparser.UNNAMED_SECTION):
    return getCfgCommon("getboolean", option, default, section)

def getCfg(option, default=None, section=configparser.UNNAMED_SECTION):
    return getCfgCommon("get", option, default, section)

LogFile                  = getCfg("LogFile", "")

WarpxInputFile           = getCfg("WarpxInputFile", WarpxInputFile)
UseMpi               = getCfgBool("UseMpi", UseMpi)
ExecBase                 = getCfg("ExecBase", ExecBase)
ExecDim                  = getCfg("ExecDim", ExecDim)
FullCommand              = getCfg("FullCommand", FullCommand)


TotalSimSteps        = int(getCfg("Steps", TotalSimSteps))
TotalSimTime       = float(getCfg("Time", TotalSimTime))
UpdateInterval     = float(getCfg("UpdateInterval", UpdateInterval))

WaitForStart         = getCfgBool("WaitForStart", WaitForStart)
WaitForData          = getCfgBool("WaitForData", WaitForData)
SkipFooter           = getCfgBool("SkipFooter", SkipFooter)
DontWaitForFooter    = getCfgBool("DontWaitForFooter", DontWaitForFooter)

UseWarpxOutputFile   = getCfgBool("UseWarpxOutputFile", False)
WarpxOutputFile          = getCfg("WarpxOutputFile", WarpxOutputFile)

UseStdin             = getCfgBool("UseStdin", UseStdin)

BlockingInput = True

try:
    Log = open(LogFile, "w")
except Exception as e:
    error("An exception occured while opening the log file '{0}':".format(LogFile))
    error(1, e)

InputData = None

if UseStdin:
    InputData = sys.stdin
    IsFifo = True
elif UseWarpxOutputFile:
    debug("Opening WarpX output file: '{}'".format(WarpxOutputFile))
    try:
        InputData = open(WarpxOutputFile, "r")
    except Exception as e:
        if WaitForStart or WaitForData:
            warning("Cannot open data file '{}' for reading, trying to create it...".format(WarpxOutputFile))
            warning(1, e)
            try:
                open(WarpxOutputFile, "x")
            except Exception as e:
                critical("Cannot open nor create data file '{}'. Aborting.".format(WarpxOutputFile))
                critical(1, e)
                exit(1)
            try:
                InputData = open(WarpxOutputFile, "r")
            except Exception as e:
                critical("Cannot open created data file '{}'. Aborting.".format(WarpxOutputFile))
                critical(1, e)
                exit(1)
#            WaitForData = True # Warpx is surely not sending data yet
        else:
            critical("Cannot open data file '{}'. Aborting.".format(WarpxOutputFile))
            critical(1, e)
            exit(1)
    debug("File '{}' successfully opened.".format(WarpxOutputFile))
    if pathlib.Path(WarpxOutputFile).is_fifo():
        IsFifo = True
else:
    Command = []

    if FullCommand == "":
        if UseMpi:
            Command.append("mpirun")

        Command.append(ExecBase + ExecDim)

        if not os.access(WarpxInputFile, os.R_OK):
            critical("Warpx input file \"{0}\" is not readable. Aborting.".format(WarpxInputFile))
            exit(1)

        Command.append(WarpxInputFile)
    else:
        Command = FullCommand.split(' ')

    RunMsg = "|   Running WarpX 3D with the following command: {0}   |".format(Command)
    RunMsgLen = len(RunMsg)

    Panel = "-" * RunMsgLen
    debug(Panel)
    debug(RunMsg)
    debug(Panel)

    try:
        WarpxSubproc = subprocess.Popen(args=Command,stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    except Exception as e:
        critical("Cannot create a subprocess to get its output. Aborting.")
        critical(1, e)
        exit(1)

    InputData = WarpxSubproc.stdout
    IsFifo = True


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
ReNum   = regex.compile("[+-]?(?:[0-9]+(?:\\.[0-9]+)?|\\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
#ReNum = regex.compile("[0-9]+(.[0-9]+(e[+-][0-9]+)?)?")

WaitForDataStart = time.time()
debug("\n      Start waiting for WarpX Data...\n")

while 1:
    if StartTime < 0:
        WaitingFor = time.time() - WaitForDataStart
        if WaitingFor > 0:
            print("\r   Waiting for WarpX to start sending data for: {}".format(str(datetime.timedelta(seconds=WaitingFor))), end='')

    OutputLine = InputData.readline()
    if OutputLine == "":
        #print("Read null string")
        if (IsFifo):
            #print("Blocking input")
            if WaitForStart and StartTime < 0:
                time.sleep(UpdateInterval)
                continue
            break
        elif WaitForData or (WaitForStart and StartTime < 0):
            #print("Waiting for data")
            time.sleep(UpdateInterval)
            continue
        break

    if StartTime < 0:
        StartTime = time.time()
        print("\n   Got data, starting processing.\n")

    try:
        if Log.isOpen():
            Log.write(OutputLine)
    except Exception:
        pass


    if MainUpdated and SecondUpdated:
        CurrentTime = time.time()
        if CurrentTime - LastUpdated > UpdateInterval:
            LastUpdated = CurrentTime
            MainUpdated = False
            SecondUpdated = False
        else:
            SkipMain = True


    if not Footer and Re1.search(OutputLine):
        if SkipMain:
            continue
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
        if TotalSimSteps > 0:
            RemainingSteps = TotalSimSteps-Step
            StepsProgress = int(Step/TotalSimSteps*100)
            StepsETA = Delta*RemainingSteps
            MeanStepETA += StepsETA

        RemainingSimTime = -1
        TimeProgress = -1
        TimeETA = -1
        if TotalSimTime > 0:
            RemainingSimTime = TotalSimTime-SimulationElapsed
            TimeProgress = int(SimulationElapsed/TotalSimTime*100)
            RealToSimTime = Delta/SimulationDelta
            TimeETA = RealToSimTime*RemainingSimTime
            MeanTimeETA += TimeETA

        Steps = Step

        EffElapsed = int(PureElapsed/Elapsed*100)
        EffDelta = int(PureDelta/Delta*100)

        StepETAStr = str(datetime.timedelta(seconds=StepsETA))
        StepsMsg = "|   Step:  {0:^15} / {1:^15} : {2:^15} ({3:>3}%), ETA: {4:>20}           ".format(Step, TotalSimSteps, RemainingSteps, StepsProgress, StepETAStr)

        TimeETAStr = str(datetime.timedelta(seconds=TimeETA))
        TimeMsg = "|   Sim time: {0:^10.2e}   /    {1:^10.2e}   :   {2:^10.2e}    ({3:>3}%), ETA: {4:>20}          ".format(SimulationElapsed, TotalSimTime, RemainingSimTime, TimeProgress, TimeETAStr)

        ElapsedStr = str(datetime.timedelta(seconds=Elapsed))
        Time2Msg = "|   Elapsed: {0}, delta: {1:.2f} ({2:.2e}), eff: elapsed: {3}%, delta: {4}%          ".format(ElapsedStr, Delta, SimulationDelta, EffElapsed, EffDelta)

        print(end='\r\033[A\033[A\033[A\033[A\033[A')
        print(StepsMsg,)
        print(TimeMsg,)
        print(Time2Msg)
        print("|")
        print("+-----------------------------------------------------------------------------+")

        PreviousTime = CurrentTime
        MainUpdated = True

    elif Re2.search(OutputLine):
        nums = ReNum.findall(OutputLine)
        #print(nums)

        PureElapsed = float(nums[0])
        PureDelta = float(nums[1])
        SecondUpdated = True

    elif Header == True and ReHead.match(OutputLine):
        print("+-----------------------------------------------------------------------------+")
        print("|                            Time statistics:                                 |")
        print("+-----------------------------------------------------------------------------+")
        print("|", end='\n\n\n\n\n\n')
        Header = False

    elif Footer == False and ReFoot.match(OutputLine):
        Footer = True
        if SkipFooter:
            break
        if WaitForData:
            WaitForData = False
            time.sleep(UpdateInterval) # The last wait

    if Header or Footer:
        print(OutputLine, end='')

    if MainUpdated and SecondUpdated:
        CurrentTime = time.time()
        if CurrentTime - LastUpdated > UpdateInterval:
            LastUpdated = CurrentTime
            MainUpdated = False
            SecondUpdated = False

"""print(MeanStepETA, MeanTimeETA, MeanTest, Steps)

MeanStepETA /= Steps
MeanTimeETA /= Steps
MeanTest /= Steps

print(MeanStepETA, MeanTimeETA, MeanTest)"""

FMsg = "Finished in " + str(datetime.timedelta(seconds=CurrentTime-StartTime))
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
