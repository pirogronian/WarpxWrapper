#!/usr/bin/python -u

import enum
import argparse
import os
import sys
import time
from WarpxWrapper import ConfigManager, IncludeAction, Logger, Verbosity, WarpxWrapper, SourceNames, System

DefaultWarpxInputFileName = "input"

class Config:
    MaxParamLength = 0
    LogLevel = "info"
    Quiet = False
    ErrorIsFatal = True
    UpdateInterval = 0.5
    StorageInterval = 5.0
    DontRun = False

    LogFile = "Log"
    MaxLogSize = 0
    MaxLogFileSize = 0
    StoragePath = "diags"

    MaxStep = -1
    MaxTime = -1.0

    Source = "command"

    ExecBase = "warpx."
    ExecDim = "3d"

    Executable = ""
    Args = []
    Command = ""

    Mpi = -1

    InputFile = ""
    IsFifo = True

    PID = 0
    AbortOnExit = False

    SkipMain = False
    SkipFooter = False
    DontWaitForFooter = True
    NonDestructivePrint = False

    ProgressBar = True

    BreakKey = "\x1b"
    ISOKey = "f"
    NonDestructivePrintKey = "d"
    AvgKey = 'a'
    RawModeKey = 'r'
    ProgressBarKey = 'p'
    PauseKey = ' '

Logger = Logger("WarpxWrapper", Config)

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

def setLogLevel(level):
    Logger.Level = level

def getLogLevel():
    return Logger.Level

CM = ConfigManager(
    Config,
    Logger,
    Error = Error,
    Description = "Small script for showing realtime WarpX time and progress stats and (optionally) to help running it.")

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

CM.Parser.add_argument("-I", "--include", nargs='+', action=IncludeAction, metavar="python_file")

class CommandAction(argparse.Action):
    def __init__(self, option_strings, dest, **kwargs):
        kwargs.pop("VarName")
        super().__init__(option_strings, dest, **kwargs)
    def __call__(self, parser, namespace, value, option_string):
        Config.Command = value
        Logger.Debug("Command line: set Command to {}".format(value))
#parser.add_argument("-s", "--source", nargs=1, action=SourceAction, choices=Sources.keys())

def InitParams():
    global CM
    CM.AddParam("LogLevel", "-v", "--verbosity",
                const='debug', choices=Verbosity.keys(),
                help = "Verbosity level. In include files don't use associated variable directly, use getLogLevel() and setLogLevel() instead.")
    CM.AddParam("Quiet", "-q", "--quiet", const = True, help = "Quiet mode. Turns off UI printing.")
    CM.AddParam("DontRun", "-r", "--dont-run", const = True, help = "Stops just before main loop. Useful for debugging.")
    CM.AddParam("ErrorIsFatal", "--error-fatal", const = True, help = "Whether to exit on errors.")
    CM.AddParam("LogFile", "-l", "--log-file", metavar="log_file_path")
    CM.AddParam("MaxLogSize", "--max-log-size", metavar="size")
    CM.AddParam("MaxLogFileSize", "--max-log-file-size", metavar="size")
    CM.AddParam("StoragePath", "-o", "--storage", metavar="storage_path")
    CM.AddParam("NonDestructivePrint", "-d", "--non-destructive-print", const = True)
    CM.AddParam("ProgressBar", "-b", "--progress-bar", const = True)
    CM.AddParam("UpdateInterval", "-u", "--upd-int", "--update-interval", metavar="seconds")
    CM.AddParam("StorageInterval", "--st--int", "--storage-interval", metavar="seconds")
    CM.AddParam("MaxStep", "-x", "--max-steps")
    CM.AddParam("MaxTime", "-t", "--max-time")
    CM.AddParam("SkipMain", "-a", "--skip-main-loop", const = True)
    CM.AddParam("SkipFooter", "-f", "--skip-footer", const = True)
    CM.AddParam("DontWaitForFooter", "--dont-wait-for-footer", const = True)
    CM.AddParam("Source", "-s", "--source", choices=SourceNames.keys())
    CM.AddParam("PID", "-p", "--pid")
    CM.AddParam("AbortOnExit", "-k", "--abort-on-exit", const = True)
    CM.AddParam("InputFile","-i", "--input-file")
    CM.AddParam("IsFifo", "--fifo", "--pipe", const = True)
    CM.AddParam("ExecBase", "--exec-base")
    CM.AddParam("ExecDim", "--dim", "--exec-dim")
    CM.AddParam("Executable", "--executable")
    CM.AddParam("Mpi", "-m", "--mpi", default = 0, const = 1, metavar="num_processes")
    CM.AddParam("Args", "--args", nargs="+")
    CM.AddParam("Command", "-c", "--command", nargs="+", action=CommandAction)
    CM.Parser.add_argument("command", nargs="*")

def InitDefaultConfig():
    global CM
    global Logger
    DefaultConfigFile = "config.py"
    if System.IsReadable(DefaultConfigFile): # Always try, never cry.
        CM.IncludeFile(DefaultConfigFile)
    else:
        Logger.Debug(f"Cannot read default config file: '{DefaultConfigFile}'")

def main():
    global CM
    global Logger

    ret = 0

    InitParams()
    InitDefaultConfig()

    args = CM.Parse(sys.argv[1:])
    if len(args.command) > 0:
        Config.Command = args.command

    PrintParams()


    WW = WarpxWrapper(Config, Logger)

    return WW.Run()

if __name__ == "__main__":
    main()
