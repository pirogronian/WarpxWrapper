
import sys
import os
import subprocess
import regex
import time
import datetime
import configparser
import logging

InputFile = "input"

TotalSimSteps = -1
TotalSimTime = -1

UpdateInterval = 0.5

UseMpi = False

LogFile = "Log.txt"

OutputFile = "output.txt"
UseOutputFile = False
ExitOnEOF = False
ExitOnFooter = False
ExitOnEOFPastFooter = True

UseStdin = False

logger = logging.getLogger()

def prepareLog(prefix, arg):
    args = list(arg)
    nest = 0
    prefix += "   "
    if len(args) > 1:
        nest = args[0]
    if isinstance(nest, int) and nest > 0:
        prefix = prefix + "   " * nest
        args.pop(0)

    msg = "".join(str(item) for item in args)
    msg = prefix + msg

    return msg

def info(*args):
    msg = prepareLog("II", args)
    logger.info(msg)

def warning(*args):
    msg = prepareLog("!!", args)
    logger.warning(msg)

def error(*args):
    msg = prepareLog("EE", args)
    logger.error(msg)

def critical(*args):
    msg = prepareLog("CC", args)
    logger.critical(msg)

def exception(*args):
    msg = prepareLog("XX", args)
    logger.exception(msg)

DefaultConfigFileName = "config.ini"

ConfigFileName = ""
if len(sys.argv) > 1:
    ConfigFileName = sys.argv[1]

if not ConfigFileName:
    info("No config file provided, falling back to default: " + DefaultConfigFileName)
    ConfigFileName = DefaultConfigFileName

config = configparser.ConfigParser(allow_unnamed_section=True, allow_no_value=True)
config.read(ConfigFileName)

def getCfgCommon(name, option, default=None, section=configparser.UNNAMED_SECTION):
    method = getattr(config, name)
    try:
        val = method(section, option, fallback=default)
        info("Config: {}.{} = {}".format(section, option, val))
    except Exception as e:
        warning("Warning, exception while reading config option \'{}\':".format(option))
        warning(1, e)
        val = default
    return val

def getCfgBool(option, default=None, section=configparser.UNNAMED_SECTION):
    return getCfgCommon("getboolean", option, default, section)

def getCfg(option, default=None, section=configparser.UNNAMED_SECTION):
    return getCfgCommon("get", option, default, section)

InputFile                = getCfg("inputfile", InputFile)
TotalSimSteps        = int(getCfg("steps", TotalSimSteps))
TotalSimTime       = float(getCfg("time", TotalSimTime))
UseMpi               = getCfgBool("usempi", UseMpi)
LogFile                  = getCfg("logfile", "")

UseOutputFile  = getCfgBool("useoutputfile", False)
OutputFile     =     getCfg("outputfile", OutputFile)

UseStdin       = getCfgBool("usestdin", UseStdin)

try:
    Log = open(LogFile, "w")
except Exception as e:
    warning("An exception occured while opening the log file '{0}':".format(LogFile))
    warning(1, e)

InputData = None

if UseStdin:
    InputData = sys.stdin

if not (UseOutputFile and UseStdin):
    if not os.access(InputFile, os.R_OK):
        critical("Input file \"{0}\" is not readable. Aborting.".format(InputFile))
        exit(1)

    Command = []

    if UseMpi:
        Command.append("mpirun")

    Command.append("warpx.3d")
    Command.append(InputFile)

    RunMsg = "|   Running WarpX 3D with the following command: {0}   |".format(Command)
    RunMsgLen = len(RunMsg)

    Panel = "-" * RunMsgLen
    print(Panel)
    print(RunMsg)
    print(Panel)

    WarpxSubproc = subprocess.Popen(args=Command,stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    InputData = WarpxSubproc.stdout

CurrentTime = 0
PreviousTime = 0
StartTime = time.time()

PureElapsed = 0
PureDelta = 0

Header = True
Footer = False

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

while 1:
    OutputLine = InputData.readline()
    if OutputLine == "":
        if UseOutputFile and not ExitOnEOF:
            sleep(UpdateInterval)
            continue
        break
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
            continue

    if Footer == False and ReFoot.match(OutputLine):
        Footer = True
        if ExitOnFooter:
            break
        if ExitOnEOFPastFooter:
            ExitOnEOF = True
            sleep(UpdateInterval)

    if Header or Footer:
        print(OutputLine, end='')

    if Header == True and ReHead.match(OutputLine):
        print("+-----------------------------------------------------------------------------+")
        print("|                            Time statistics:                                 |")
        print("+-----------------------------------------------------------------------------+")
        print("|", end='\n\n\n\n\n\n')
        Header = False

    if Re1.search(OutputLine):
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

    if MainUpdated and SecondUpdated:
        CurrentTime = time.time()
        if CurrentTime - LastUpdated > UpdateInterval:
            LastUpdated = CurrentTime
            MainUpdated = False
            SecondUpdated = False
        else:
            continue

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
