
import sys
import os
import subprocess
import time
import enum
import datetime
import pathlib
import stat
import pypsutil
from queue import SimpleQueue
import shlex

from WarpxWrapper import InputStream, InputTerminal, OutputStream
from WarpxWrapper import Timer
from WarpxWrapper import FormattedTime, INF
from WarpxWrapper import System
from WarpxWrapper import ControlManager
from WarpxWrapper import UI
from WarpxWrapper import WarpxDataParser
from WarpxWrapper.LimitedBlockWriter import LimitedBlockWriter
from WarpxWrapper import IterableToStr2D

def ChooseETA(ETA1, ETA2):
    if ETA1 > 0 and ETA2 > 0:
        return min(ETA1, ETA2)

    if ETA1 > 0:
        return ETA1
    return ETA2

class AccStats:
    def Reset(self):
        self.UpdNr = 0
        self.DataSize = 0
        self.PrevDataSize = 0
        self.PrevStepDataSize = 0

        self.DataSpeed = 0
        self.AvgDataSpeed = 0

        self.DataSpeedStep = 0
        self.AvgDataSpeedStep = 0

        self.StepESA = 0
        self.TimeESA = 0

        self.AvgStepESA = 0
        self.AvgTimeESA = 0

        self.CPUStart = 0
        self.CPUTime = 0
        self.PrevCPUTime = 0
        self.CPU = 0
        self.AvgCPU = 0

    def Recalculate(self, TimeDelta, ElapsedTime, PausedTime):
        self.UpdNr += 1
        #print(f"Upd # {self.UpdNr}. Loop: {self.Loop}.")
        #print(f"CTime: {self.CurrentTime:.2f}, prev time: {self.PrevTime:.2f}")

        self.DataDelta = self.DataSize - self.PrevDataSize
        self.CPUDelta = self.CPUTime - self.PrevCPUTime

        if TimeDelta > 0:
            self.DataSpeed = self.DataDelta / TimeDelta
            self.CPU = self.CPUDelta / TimeDelta

        if ElapsedTime > 0:
            self.AvgDataSpeed = self.DataSize / ElapsedTime

        if self.CPUStart > 0:
            self.AvgCPU = self.CPUTime / (time.time() - self.CPUStart - PausedTime)
            #print(f"Set AvgCPU: {self.CPUTime} / {time.time()} - {self.CPUStart} = / {time.time() - self.CPUStart} = {self.AvgCPU}")

        self.PrevDataSize = self.DataSize
        self.PrevCPUTime = self.CPUTime
        #print(f"DDelta: {self.DataDelta} / {self.Delta:.2f}, {self.DataSpeed:.2f}/s")

    def RecalculateStep(self, Step, StepDelta):
        self.DataStepDelta = self.DataSize - self.PrevStepDataSize
        if StepDelta > 0:
            self.DataSpeedStep = self.DataStepDelta / StepDelta
        if Step > 0:
            self.AvgDataSpeedStep = self.DataSize / Step


class StorageStats:
    def Reset(self):
        self.RawSize = 0
        self.Size = 0
        self.StartSize = -1
        self.Speed = 0
        self.ESA = 0
        self.AvgESA = 0

    def Recalculate(self, Elapsed):
        self.Size = self.RawSize - self.StartSize
        if Elapsed > 0:
            self.Speed = self.Size / Elapsed
            #print(f"St Speed: {self.Speed:.2f}, {SizeStr(self.Size)} - {SizeStr(self.StartSize)} = {SizeStr(self.Size - self.StartSize)} / {self.Elapsed:.4f}")


class SimulationStatus:
    def __init__(self, AccStats, StorageStats):
        self.AccStats = AccStats
        self.StorageStats = StorageStats

    def Reset(self):
        self.Header = True
        self.Main = False
        self.StatsUpdated = False
        self.Footer = False

        self.StartRealTime = time.time()
        self.ElapsedRealTime = 0
        self.Paused = False
        self.PausedAt = 0
        self.PausedRealTime = 0
        self._PausedRealTime = 0

        self.Step = -1 # These two are replenished externally
        self.Time = -1

        self.MaxStep = -1 # These two are set once at the beginning
        self.EstMaxStep = -1
        self.AvgEstMaxStep = -1
        self.MaxTime = -1
        self.EstMaxTime = -1
        self.AvgEstMaxTime = -1

        self.StepsLeft = -1
        self.EstStepsLeft = -1
        self.TimeLeft = -1
        self.EstTimeLeft = -1

        self.StepsProgress = -1
        self.TimeProgress = -1

        self.CurrentRealTime = 0 # This is replenished automatically

        self.PrevStep = 0
        self.PrevTime = 0
        self.PrevRealTime = 0

        self.StepDelta = -1
        self.TimeDelta = -1 # This also is replenished externally
        self.RealTimeDelta = -1

        self.StepSpeed = 0
        self.TimeSpeed = 0

        self.AvgStepSpeed = 0
        self.AvgTimeSpeed = 0

        self.StepETA = -1
        self.TimeETA = -1

        self.AvgStepETA = -1
        self.AvgTimeETA = -1

        self.TimePerStep = -1
        self.StepsPerTime = -1
        self.AvgTimePerStep = -1
        self.AvgStepsPerTime = -1

        self.AccStats.Reset()
        self.StorageStats.Reset()

    def Pause(self):
        if self.Paused:
            return
        self.PausedAt = time.time()
        self.Paused = True

    def Resume(self):
        if not self.Paused:
            return
        self._PausedRealTime += time.time() - self.PausedAt
        self.Paused = False

    def CompElapsedRealTime(self):
        if self.Paused:
            #print(f"{self.ElapsedRealTime} = {self.PausedAt} - {self.StartRealTime} - {self.PausedRealTime}")
            return self.PausedAt - self.StartRealTime - self._PausedRealTime
        #print(f"{self.ElapsedRealTime} = {time.time()} - {self.StartRealTime} - {self.PausedRealTime}")
        return time.time() - self.StartRealTime - self._PausedRealTime

    def CompPausedRealTime(self):
        if self.Paused:
            return time.time() - self.PausedAt + self._PausedRealTime
        return self._PausedRealTime

    def CalculateETA(self):
        self.StepDelta = self.Step - self.PrevStep
        # TimeDelta was provided externally, but is no longer
        self.TimeDelta = self.Time - self.PrevTime

        #print(f"Step: {self.Step}, Time: {self.Time}")
        #print(f"PrevStep: {self.PrevStep}, PrevTime: {self.PrevTime}")
        #print(f"Deltas: step {self.StepDelta}, time {self.TimeDelta}")

        self.RealTimeDelta = self.ElapsedRealTime - self.PrevRealTime

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
        else:
            self.StepETA = INF
        if self.TimeSpeed > 0:
            self.TimeETA = self.TimeLeft / self.TimeSpeed
        else:
            self.TimeETA = INF

    def CalculateAvgETA(self):
        self.AvgStepSpeed = self.Step / self.ElapsedRealTime
        if self.AvgStepSpeed > 0:
            self.AvgStepETA = self.StepsLeft / self.AvgStepSpeed
        else:
            self.AvgStepETA = INF

        self.AvgTimeSpeed = self.Time / self.ElapsedRealTime
        if self.AvgTimeSpeed > 0:
            self.AvgTimeETA = self.TimeLeft / self.AvgTimeSpeed
        else:
            self.AvgTimeETA = INF

    def CalculateESA(self):
        ETA = 0
        AvgETA = 0

        ETA = ChooseETA(self.StepETA, self.TimeETA)
        AvgETA = ChooseETA(self.AvgStepETA, self.AvgTimeETA)

        #print(f"SimStatus.StepsLeft: {self.SimSeq.Current.StepsLeft}, AccStats.DataStepSpeed: {self.AccStats.DataStepSpeed}")
        if self.StepsLeft >= 0 and self.AccStats.DataSpeedStep >= 0:
            self.AccStats.StepESA = self.AccStats.DataSize + self.StepsLeft * self.AccStats.DataSpeedStep

        #print(f"SimStatus.TimeETA: {self.SimSeq.Current.TimeETA}, AccStats.DataSpeed: {self.AccStats.DataSpeed}")

        self.AccStats.TimeESA = self.AccStats.DataSize + ETA * self.AccStats.DataSpeed

        self.AccStats.AvgStepESA = self.AccStats.DataSize + self.StepsLeft * self.AccStats.AvgDataSpeedStep

        self.AccStats.AvgTimeESA = self.AccStats.DataSize + AvgETA * self.AccStats.AvgDataSpeed

        self.StorageStats.ESA = self.StorageStats.Size + self.StorageStats.Speed * ETA

        self.StorageStats.AvgESA = self.StorageStats.Size + self.StorageStats.Speed * AvgETA

    def Recalculate(self):
        #print(f"TimeDelta: {self.TimeDelta}, StepDelta: {self.StepDelta}")

        self.ElapsedRealTime = self.CompElapsedRealTime()
        self.PausedRealTime = self.CompPausedRealTime()

        self.RealTimeDelta = self.ElapsedRealTime - self.PrevRealTime

        if self.Step >= 0 and self.MaxStep > 0:
            self.StepsLeft = self.MaxStep - self.Step

        if self.Time >= 0 and self.MaxTime > 0:
            self.TimeLeft = self.MaxTime - self.Time

        if self.MaxStep > 0:
            self.StepsProgress = self.Step / self.MaxStep
        else:
            self.StepsProgress = -1
        if self.MaxTime > 0:
            self.TimeProgress = self.Time / self.MaxTime
        else:
            self.TimeProgress = -1

        self.CalculateETA()
        if self.ElapsedRealTime > 0:
            self.CalculateAvgETA()

        self.AccStats.Recalculate(self.RealTimeDelta, self.ElapsedRealTime, self.PausedRealTime)
        self.AccStats.RecalculateStep(self.Step, self.StepDelta)
        self.CalculateESA()

        self.PrevStep = self.Step
        self.PrevTime = self.Time
        self.PrevRealTime = self.ElapsedRealTime


class SimSequenceStatus:
    def __init__(self, CurrentSim, AccStats, StorageStats):
        self.Current = CurrentSim
        self.AccStats = AccStats
        self.StorageStats = StorageStats

    def Reset(self):
        self.Iteration = 0
        self.Step = 0
        self.Time = 0.0

        self.MaxStep = -1
        self.MaxTime = -1
        self.StepsLeft = -1
        self.TimeLeft = -1
        self.EstMaxStep = -1
        self.AvgEstMaxStep = -1
        self.MaxTime = -1
        self.EstMaxTime = -1
        self.AvgEstMaxTime = -1

        self.StepsLeft = -1
        self.EstStepsLeft = -1
        self.TimeLeft = -1
        self.EstTimeLeft = -1

        self.StepsProgress = -1
        self.TimeProgress = -1

        self.ElapsedRealTime = 0
        self.PausedRealTime = 0

        self.AvgStepSpeed = 0
        self.AvgTimeSpeed = 0
        self.AvgStepsPerTime = 0
        self.AvgTimePerStep = 0

        self.StepETA = -1
        self.TimeETA = -1

        self.AvgStepETA = -1
        self.AvgTimeETA = -1

        self.PrevStep = 0
        self.PrevTime = 0
        self.PrevRealTime = 0

        self.StepSpeed = -1
        self.TimeSpeed = -1

        self.StepDelta = -1
        self.TimeDelta = -1
        self.RealTimeDelta = -1

        self.AccStats.Reset()
        self.StorageStats.Reset()

    def Next(self):
        self.Iteration += 1
        self.PrevStep = self.Step
        self.PrevTime = self.Time
        self.PrevRealTime = self.ElapsedRealTime
        self.PrevPausedTime = self.PausedRealTime

    def CompElapsedRealTime(self):
        return self.PrevRealTime + self.Current.CompElapsedRealTime()

    def CompPausedRealTime(self):
        return self.PrevPausedTime + self.Current.CompPausedRealTime()

    def CalculateESA(self):
        ETA = 0
        AvgETA = 0

        ETA = ChooseETA(self.StepETA, self.TimeETA)
        AvgETA = ChooseETA(self.AvgStepETA, self.AvgTimeETA)

        #print(f"SimStatus.StepsLeft: {self.SimSeq.Current.StepsLeft}, AccStats.DataStepSpeed: {self.AccStats.DataStepSpeed}")
        self.AccStats.StepESA = self.AccStats.DataSize + self.StepsLeft * self.AccStats.DataSpeedStep

        #print(f"SimStatus.TimeETA: {self.SimSeq.Current.TimeETA}, AccStats.DataSpeed: {self.AccStats.DataSpeed}")
        self.AccStats.TimeESA = self.AccStats.DataSize + ETA * self.AccStats.DataSpeed

        self.AccStats.AvgStepESA = self.AccStats.DataSize + self.StepsLeft * self.AccStats.AvgDataSpeedStep

        self.AccStats.AvgTimeESA = self.AccStats.DataSize + AvgETA * self.AccStats.AvgDataSpeed

        self.StorageStats.ESA = self.StorageStats.Size + self.StorageStats.Speed * ETA

        self.StorageStats.AvgESA = self.StorageStats.Size + self.StorageStats.Speed * AvgETA

    def Recalculate(self, MaxStep = -1, MaxTime = -1):
        self.Current.Recalculate()

        if MaxStep < 0:
            MaxStep = self.Current.MaxStep
        if MaxTime < 0:
            MaxTime = self.Current.MaxTime
        self.MaxStep = MaxStep
        self.MaxTime = MaxTime

        self.StepSpeed = self.Current.StepSpeed
        self.TimeSpeed = self.Current.TimeSpeed

        self.StepDelta = self.Current.StepDelta
        self.TimeDelta = self.Current.TimeDelta
        self.RealTimeDelta = self.Current.RealTimeDelta

        self.StepsPerTime = self.Current.StepsPerTime
        self.TimePerStep = self.Current.TimePerStep

        self.AvgStepsPerTime = self.Current.AvgStepsPerTime
        self.AvgTimePerStep = self.Current.AvgTimePerStep

        self.Step = self.PrevStep + self.Current.Step
        self.Time = self.PrevTime + self.Current.Time
        self.ElapsedRealTime = self.CompElapsedRealTime()

        if self.ElapsedRealTime > 0:
            self.AvgStepSpeed = self.Step / self.ElapsedRealTime
            self.AvgTimeSpeed = self.Time / self.ElapsedRealTime

        if self.Time > 0:
            self.AvgStepsPerTime = self.Step / self.Time

        if self.Step > 0:
            self.AvgTimePerStep = self.Time / self.Step

        if MaxStep > 0:
            self.StepsLeft = MaxStep - self.Step
            self.StepsProgress = self.Step / MaxStep

            if self.Current.StepSpeed > 0:
                self.StepETA = self.StepsLeft / self.Current.StepSpeed
            else:
                self.StepETA = INF

            if self.Current.AvgStepSpeed > 0:
                self.AvgStepETA = self.StepsLeft / self.AvgStepSpeed
            else:
                self.AvgStepETA = INF

            if MaxTime < 0:
                if self.Current.TimePerStep > 0:
                    self.EstMaxTime = self.StepsLeft * self.Current.TimePerStep
                else:
                    self.EstMaxTime = INF

                if self.AvgTimePerStep > 0:
                    self.AvgEstMaxTime = self.StepsLeft * self.AvgTimePerStep
                else:
                    self.AvgEstMaxTime = INF

        if MaxTime > 0:
            self.TimeLeft = MaxTime - self.Time
            self.TimeProgress = self.Time / MaxTime

            if self.TimeSpeed > 0:
                self.TimeETA = self.TimeLeft / self.TimeSpeed
            else:
                self.TimeETA = INF

            if self.AvgTimeSpeed > 0:
                self.AvgTimeETA = self.TimeLeft / self.AvgTimeSpeed
            else:
                self.AvgTimeETA = INF

            if MaxStep < 0:
                if self.StepsPerTime >= 0:
                    self.EstMaxStep = self.TimeLeft * self.StepsPerTime
                else:
                    self.EstMaxStep = INF

                if self.AvgStepsPerTime:
                    self.AvgEstMaxStep = self.TimeLeft * self.AvgStepsPerTime

        self.AccStats.Recalculate(self.RealTimeDelta, self.ElapsedRealTime, self.PausedRealTime)
        self.AccStats.RecalculateStep(self.Step, self.StepDelta)
        self.CalculateESA()


class SystemStats:
    FreeMemory = 0
    FreeStorage = 0


class State:
    def Reset(self):
        self.SkipMain = False
        self.ProcessWasFinding = False
        self.Footer = False

class SourceType(enum.Enum):
    DEFAULT = 0 # It means the COMMAND
    COMMAND = 1
    FILE    = 2
    STDIN   = 3

SourceNames = {
    "command": SourceType.COMMAND,
    "file": SourceType.FILE,
    "stdin": SourceType.STDIN
    }

class WarpxWrapper:
    UpdateInterval = 0.5
    StartTime = -1
    PausedAt = -1
    Pausedtime = 0
    Paused = False
    WarpxProcess = None
    Finishing = False
    Raw = False
    SimSeq = False

    def __init__(self, Config, Logger):
        self.Config = Config
        self.Logger = Logger
        self.State = State()
        self.SimSeq = SimSequenceStatus(SimulationStatus(AccStats(), StorageStats()), AccStats(), StorageStats())
        self.SystemStats = SystemStats()
        self.Control = ControlManager()
        self.EventQueue = SimpleQueue()
        self.ControlInput = InputTerminal(EventQueue = self.EventQueue, Event = 2, Interval = 0, UseBlessed = False, force_styling=True)
        self.UI = UI(self.SimSeq, self.SystemStats, self.ControlInput, self.Config)
        self.UpdateTimer = Timer("UpdateInterval")
        self.StorageTimer = Timer("StorageInterval")
        self.DataParser = WarpxDataParser(self.SimSeq.Current, self.Logger)
        self.PausedTime = 0

    def ResetState(self):
        self.UserBreak = False
        self.WarpxProcess = None
        self.State.Reset()
        self.SimSeq.Current.Reset()
        self.SimSeq.Current.MaxStep = self.Config.MaxStep
        self.SimSeq.Current.MaxTime = self.Config.MaxTime
        self.UI.ResetState()


    def Error(self, *args):
        if args:
            self.Logger.Error(*args)
        if self.Config.ErrorIsFatal:
            self.Logger.Error(" ^^^^ An error occured, aborting. ^^^^")
            exit(1)

    def Fatal(self, *args):
        if args:
            self.Logger.Critical(*args)
        self.Logger.Critical(" ^^^^ An error occured, aborting. ^^^^")
        exit(1)

    def CallEventHandler(self, name, *args, **kargs):
        if hasattr(self.Config, "EventHandler"):
            if hasattr(self.Config.EventHandler, name):
                return getattr(self.Config.EventHandler, name)(*args, **kargs)

    def RegisterActions(self):
        self.Control.Register(self.Config.BreakKey, self.DoUserBreak)
        self.Control.Register(self.Config.SeqKey, self.UI.SwitchSeq)
        self.Control.Register(self.Config.FormatKey, self.UI.SwitchFormat)
        self.Control.Register(self.Config.AvgKey, self.UI.SwitchAvg)
        self.Control.Register(self.Config.RawOutputKey, self.SwitchRawOutput)
        self.Control.Register(self.Config.NonDestructivePrintKey, self.UI.SwitchDestrictive)
        self.Control.Register(self.Config.ProgressBarKey, self.SwitchProgressBar)
        self.Control.Register(self.Config.PauseKey, self.SwitchRunningState)
        self.Control.Register(self.Config.ShorterIntervalKey, self.ShorterInterval)
        self.Control.Register(self.Config.LongerIntervalKey, self.LongerInterval)

    def PrepareStdin(self):
        self.DataInput.Input = sys.stdin
        self.ControlInput.Stream = None

    def PrepareInputFile(self):
        IsFifo = self.Config.IsFifo
        self.Logger.Debug(f"Opening WarpX output file: '{self.Config.InputFile}'")
        Path = pathlib.Path(self.Config.InputFile)
        if Path.is_file():
            if Path.is_fifo():
                IsFifo = True
            else:
                IsFifo = False
        elif Path.is_fifo():
            IsFifo = True
        else:
            if IsFifo:
                os.mkfifo(self.Config.InputFile)
            else:
                os.mknod(self.Config.InputFile, stat.S_IFREG | 0o600)
        if IsFifo:
            self.Logger.Debug("Input file is a pipe. Open it inside thread.")
            self.DataInput.Stream = self.Config.InputFile
        else:
            self.Logger.Debug("Input fle is an ordinary file. Don't exit if read zero bytes.")
            self.DataInput.Interval = "DataInterval" # Use value from Config
            try:
                DataStream = open(self.Config.InputFile, "r")
            except Exception as e:
                self.Logger.ExceptCritic(e)
                self.Fatal(f"Cannot open data file '{self.Config.InputFile}' for reading.")
            self.DataInput.Stream = DataStream
            self.Logger.Debug(f"File '{self.Config.InputFile}' successfully opened.")

    def PrepareCommand(self):
        CmdArgs = []

        if self.Config.Mpi > 0:
            CmdArgs.append("mpirun")
            if self.Config.Mpi > 1:
                CmdArgs.append("-np")
                CmdArgs.append(f"{self.Config.Mpi}")

        if type(self.Config.Command) == str and self.Config.Command != "":
            CmdArgs.extend(self.Config.Command.split())
        elif type(self.Config.Command) == list and len(self.Config.Command) > 0:
            for arg in self.Config.Command:
                subargs = shlex.split(arg)
                CmdArgs.extend(subargs)
        else:
            if self.Config.Executable != "":
                CmdArgs.append(self.Config.Executable)
            else:
                CmdArgs.append(self.Config.ExecBase + self.Config.ExecDim)

            if self.Config.InputFile == "":
                self.Error(f"Warpx input file is not defined.")
            if not System.IsReadable(self.Config.InputFile):
                self.Error(f"Warpx input file \"{self.Config.InputFile}\" is not readable.")

            CmdArgs.append(self.Config.InputFile)

            CmdArgs.extend(self.Config.Args)

        self.Logger.Debug(f"Running WarpX 3D with the following command:\n" + IterableToStr2D(CmdArgs))

        try:
            self.WarpxProcess = pypsutil.Popen(args=CmdArgs,
                                        stdin=subprocess.DEVNULL,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT,
                                        text=True)
        except Exception as e:
            self.Logger.ExceptCrit(e)
            self.Fatal("Cannot create a subprocess to get its output.")

        self.DataInput.Stream = self.WarpxProcess.stdout

    def PrepareSource(self):
        S = SourceNames[self.Config.Source]
        if S == SourceType.STDIN:
            self.PrepareStdin()
        elif S == SourceType.FILE:
            self.PrepareInputFile()
        else:
            self.PrepareCommand()

    def PrepareLogOutput(self):
        if self.Config.LogFile == None and self.Config.LogFile == "":
            return
        IsFifo = False
        self.Logger.Debug(f"Opening log file: '{self.Config.LogFile}'")
        Path = pathlib.Path(self.Config.LogFile)
        if Path.is_file():
            if Path.is_fifo():
                IsFifo = True
            else:
                IsFifo = False
        elif Path.is_fifo():
            IsFifo = True
        else:
            if IsFifo:
                os.mkfifo(self.Config.InputFile)
            else:
                self.LogOutput = LimitedBlockWriter(MaxSize = self.Config.MaxLogSize, BlockSize = self.Config.MaxLogFileSize, FileName = self.Config.LogFile)
                self.LogOutput.Flush = True
                self.Logger.Debug("Set limited block writer as data log output.")
                return
        self.LogOutput = OutputStream()
        self.LogOutput.Flush = True
        if IsFifo:
            self.Logger.Debug("Log file is a pipe. Open it inside thread.")
            self.LogOutput.Stream = self.Config.InputFile
        else:
            self.Logger.Debug("Log file is an ordinary file.")
            LogStream = None
            try:
                LogStream = open(self.Config.LogFile, "w")
            except Exception as e:
                self.Logger.ExceptError(e)
                self.Error(f"Cannot open log file '{self.Config.LogFile}' for writing.")
            self.LogOutput.Stream = LogStream
            self.Logger.Debug(f"File '{self.Config.LogFile}' successfully opened.")

    def PrepareDataStream(self):
        self.DataInput = InputStream(Lines = True, EventQueue = self.EventQueue, Event = 1)
        self.DataInput.QueueSizeThreshold = 100

    def ActivateDataStream(self):
        self.Logger.Debug("Activating non-blocking data input.")
        if self.DataInput.Activate() == 1:
            raise RuntimeError("Another thread is already active!")
        self.Logger.Debug(1, f"Input activity status: {self.DataInput.IsActive()}.")

    def ActivateStreams(self):
        if self.ControlInput.Stream != None:
            self.Logger.Debug("Activating non-blocking control input.")
            self.ControlInput.Activate()
            self.Logger.Debug(1, f"Input Activity status: {self.ControlInput.IsActive()}.")
        else:
            self.Logger.Debug("Stdin used for data, don't activate control input.")

        if self.LogOutput != None:
            self.Logger.Debug("Activating non-blocking log output.")
            self.LogOutput.Activate()
            self.Logger.Debug(1, f"Output Activity status: {self.LogOutput.IsActive()}.")

    def CloseDataStream(self):
        self.DataInput.Close(0)
        #if self.LogOutput != None:
        #    self.LogOutput.Close()

    def CloseLogStream(self):
        if self.LogOutput != None:
            self.LogOutput.Close()

    def OnKey(self, Key):
        if not self.Control.Dispatch(Key):
            self.UI.Message(f"Key: {Key.encode()}")
        if not (self.UserBreak or self.Config.Quiet or self.Raw):
            self.UI.Update(Force = True)

    def ProcessControlInput(self):
        while 1:
            Key = self.ControlInput.Read()
            if Key == None:
                break
            self.OnKey(Key)
            if self.UserBreak:
                break

    def Pause(self):
        if self.WarpxProcess != None:
            System.PauseProcTree(self.WarpxProcess)
        self.SimSeq.Current.Pause()
        self.UI.Status("Paused")

    def Resume(self):
        if self.WarpxProcess != None:
            System.ResumeProcTree(self.WarpxProcess)
        self.SimSeq.Current.Resume()
        self.UI.Status()
        self.UI.Message("Resumed")

    def SwitchRunningState(self):
        if self.SimSeq.Current.Paused:
            self.Resume()
        else:
            self.Pause()
        self.SimSeq.Current.Recalculate()
        self.SimSeq.Recalculate(self.Config.SeqMaxStep, self.Config.SeqMaxTime)

    def ShorterInterval(self):
        self.Config.UpdateInterval = self.Config.UpdateInterval / 1.5
        self.UI.MsgCurrentUpdateInterval()

    def LongerInterval(self):
        self.Config.UpdateInterval = self.Config.UpdateInterval * 1.5
        self.UI.MsgCurrentUpdateInterval()

    def SwitchRawOutput(self):
        self.Raw = not self.Raw
        if not self.Raw:
            self.UI.First = True
        self.UI.Message(f"Raw mode: {self.Raw}")

    def SwitchProgressBar(self):
        self.Config.UI.ProgressBar = not self.Config.UI.ProgressBar

    def DoUserBreak(self):
        self.UI.PrintLine("\n\n")
        self.Logger.Info(f"Breaking on user demand.")
        self.UserBreak = True

    def PrepareUI(self):
        self.UI.MinLen = 79
        self.UI.CacheMaxLen()
        self.UI.Setup()

    def UpdateSystemStats(self):
        mem = pypsutil.virtual_memory()
        self.SystemStats.FreeMemory = mem.available
        try:
            st = pypsutil.disk_usage(self.Config.StoragePath)
            self.SystemStats.FreeStorage = st.free
        except FileNotFoundError:
            pass

    def InitStorageStats(self, StorageStats):
        if StorageStats.StartSize < 0:
            try:
                StorageStats.StartSize = System.DirSize(self.Config.StoragePath)
            except FileNotFoundError:
                self.Logger.Warning(f"'{self.Config.StoragePath}' - file not found.")

    def UpdateStorageStats(self, StorageStats, Elapsed):
        try:
            StorageStats.RawSize = System.DirSize(self.Config.StoragePath)
            StorageStats.Recalculate(Elapsed)
        except FileNotFoundError:
            pass

    def Update(self, Force = False):
        self.InitStorageStats(self.SimSeq.StorageStats)
        self.InitStorageStats(self.SimSeq.Current.StorageStats)

        if self.StorageTimer.Expired():
            self.UpdateStorageStats(self.SimSeq.StorageStats, self.SimSeq.ElapsedRealTime)
            self.UpdateStorageStats(self.SimSeq.Current.StorageStats, self.SimSeq.Current.ElapsedRealTime)
            self.StorageTimer.Reset()

        if self.UpdateTimer.Expired() or Force:
            self.SimSeq.Recalculate(self.Config.SeqMaxStep, self.Config.SeqMaxTime)
            if self.WarpxProcess != None:
                    #print("Update proc info.")
                try:
                    self.ProcStats = System.GetProcTreeStats(self.WarpxProcess)
                except pypsutil.NoSuchProcess as e:
                    self.WarpxProcess = None
                self.SimSeq.AccStats.CPUStart = self.ProcStats.CrTime
                self.SimSeq.Current.AccStats.CPUStart = self.ProcStats.CrTime
                self.SimSeq.AccStats.CPUTime = self.ProcStats.CPU
                self.SimSeq.Current.AccStats.CPUTime = self.ProcStats.CPU
                self.UI.ProcStats = self.ProcStats
                    #print(str(self.ProcStats))
            else:
                self.UI.ProcStats = System.ProcTreeStats()
            self.UpdateSystemStats()

            self.UpdateTimer.Reset()

            if not (self.Config.Quiet or self.Raw):
                self.UI.Update()

    def MainLoop(self):
        self.Update()

        while not self.EventQueue.empty():
            self.EventQueue.get_nowait() # eat stalled events

        self.ProcessControlInput()

        if self.UserBreak:
            if self.StartTime < 0:
                self.StartTime = time.time()
            self.Logger.Debug("User break.")
            return 3

        if self.StartTime < 0:
            WaitingFor = time.time() - self.WaitForDataStart
            if WaitingFor > 0:
                self.UI.PrintStaticLine(f"Waiting for WarpX to start sending data for: {self.UI.FmtTime.Str(WaitingFor)}")

        #if not (Header or Footer):
        #    self.UI.Update()

        OutputLine = self.DataInput.Read()
        if OutputLine == None or OutputLine == "":
            #print("Read null string")
            if (self.DataInput.IsActive()):
#                print(f"DataInput active, waiting for {self.Config.UpdateInterval}.")
                Event = None
                try:
                    Event = self.EventQueue.get(timeout=self.Config.UpdateInterval)
                except Exception as e:
                    #Logger.Debug("Exception while waiting for event.")
                    #Logger.ExceptDebug(e)
                    pass
#                t = type(Event)
#                print("Got event:", Event, t)
#                if t == float:
#                    print("Time delay:", time.time() - Event)
                return 0 # So all interactivity must take place earlier
            else:
                self.Logger.Debug("DataInput inactive, finishing.")
                return 1
        if self.Raw:
            print(OutputLine, end = '')

        self.SimSeq.AccStats.DataSize += len(OutputLine)
        self.SimSeq.Current.AccStats.DataSize += len(OutputLine)

        #print(f"Increasing data size: {AccStats.DataSize}.")

        #print(f"{not self.State.ProcessWasFinding} and {self.WarpxProcess == None} and {self.Config.Source == SourceType.FILE} and {self.Config.PID}")
        if OutputLine \
            and not self.State.ProcessWasFinding \
                and self.WarpxProcess == None \
                    and SourceNames[self.Config.Source] == SourceType.FILE \
                        and self.Config.PID == 0:
            Ps = System.FileUsers(self.Config.InputFile, ["w", "a"])
#            print("")
#            print(Ps)
            Me = pypsutil.Process()
            for P in Ps:
                if P != Me:
                    self.WarpxProcess = P
                    self.Logger.Debug(f"Detected Warpx process: {self.WarpxProcess.name()} ({self.WarpxProcess.pid}).")
            if self.WarpxProcess == None:
                self.Logger.Warning("Warpx process not detected!")
            self.State.ProcessWasFinding = True


        if self.StartTime < 0:
            self.StartTime = time.time()
            self.UI.CurrentSection = UI.Section.HEADER
            self.UI.PrintLine("\nGot data, starting processing.\n")

        if self.LogOutput != None:
            self.LogOutput.Write(OutputLine)

        if self.DataParser.ParseLine(OutputLine) == 2:
            return 2

        if self.SimSeq.Current.MaxStep > 0:
            self.Config.MaxStep = self.SimSeq.Current.MaxStep
        if self.SimSeq.Current.MaxTime > 0:
            self.Config.MaxTime = self.SimSeq.Current.MaxTime

        if self.SimSeq.Current.Main == True:
            self.State.Main = True
            self.State.Header = False
            self.UI.CurrentSection = UI.Section.MAIN
        if self.SimSeq.Current.Footer and not self.State.Footer:
            self.State.Footer = True
            self.UI.CurrentSection = UI.Section.FOOTER
            self.Logger.Debug("Footer detected.")
            if self.Config.SkipFooter:
                return 1
            time.sleep(self.Config.UpdateInterval) # Let some time to the pipe to read last of data.
            self.DataInput.Interval = 0 # Don't wait for data anymore.

        if self.SimSeq.Current.Step > self.SimSeq.Current.PrevStep:
            #self.SimSeq.Recalculate(self.Config.SeqMaxStep, self.Config.SeqMaxTime)
            self.CallEventHandler("OnStep", self.SimSeq.Current.Step, self.SimSeq.Current.Time)

        if self.SimSeq.Current.Header or self.SimSeq.Current.Footer:
            print(OutputLine, end='')

        return 0

    def RunMainLoop(self):
        try:
            if self.Config.DontRun:
                Logger.Debug("Don't run. Exiting...")
                return 0
            while 1:
                if self.Config.SkipMain:
                    self.Logger.Debug("Skipping main.")
                    break

                self.ExitCode = self.MainLoop()
                if self.ExitCode > 0:
                    self.Logger.Debug(f"Exiting with code: {self.ExitCode}")
                    break

        except Exception as e:
            self.Logger.Critical("Unhandled exception, breaking main loop.")
            self.Logger.ExceptCrit(e)
            self.ExitCode = 4

        return self.ExitCode

    def Finish(self):
        self.UI.CurrentSection = UI.Section.FOOTER

        self.Resume()

        S = SourceNames[self.Config.Source]
        if (self.Config.AbortOnExit or S == SourceType.COMMAND) and self.WarpxProcess != None:
            self.Logger.Debug("Terminating WarpX.")
            self.WarpxProcess.terminate()
            time.sleep(0.1)
            self.WarpxProcess.kill()

        self.CloseDataStream()

        if not self.Config.Quiet:
            self.UI.WriteSummary(self.SimSeq.ElapsedRealTime)

        return self.CallEventHandler("OnFinish", self.ExitCode)

    def Run(self):
        self.SimSeq.Reset()
        self.PrepareUI()
        self.RegisterActions()
        self.PrepareLogOutput()
        self.ActivateStreams()
        self.ControlInput.DisableBuffering()

        try:
            while True:
                self.ResetState()
                self.CallEventHandler("OnInit")
                self.PrepareDataStream()
                self.PrepareSource()
                self.ActivateDataStream()

                if self.WarpxProcess == None and self.Config.PID > 0:
                    try:
                        self.WarpxProcess = pypsutil.Process(Config.PID)
                    except Exception as e:
                        Logger.ExceptError(e)
                        Logger.Error(f"Cannot assign Warpx process from given PID: {Config.PID}")

                self.WaitForDataStart = time.time()
                self.Logger.Debug("Start waiting for WarpX data...\n")

                self.RunMainLoop()
                if not self.Finish():
                    break

                self.SimSeq.Next()

        except Exception as e:
            self.ControlInput.RestoreBuffering()
            self.Logger.Critical("Unhandled exception occured.")
            self.Logger.ExceptCrit(e)
            self.ExitCode = 4

        finally:
            self.ControlInput.RestoreBuffering()
            self.CloseLogStream()
            self.UI.Finish()

        return self.ExitCode
