
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
from WarpxWrapper import FormattedTime
from WarpxWrapper import System
from WarpxWrapper import ControlManager
from WarpxWrapper import UI
from WarpxWrapper import WarpxDataParser
from WarpxWrapper.LimitedBlockWriter import LimitedBlockWriter
from WarpxWrapper import IterableToStr2D

class SimulationStatus:
    def Reset(self):
        self.Header = True
        self.Main = False
        self.Updated = False
        self.StatsUpdated = False
        self.Footer = False

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

        self.StartRealTime = 0
        self.ElapsedRealTime = 0

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

    def CalculateETA(self):
        self.StepDelta = self.Step - self.PrevStep
        # TimeDelta was provided externally, but is no longer
        self.TimeDelta = self.Time - self.PrevTime

        #print(f"Step: {self.Step}, Time: {self.Time}")
        #print(f"PrevStep: {self.PrevStep}, PrevTime: {self.PrevTime}")
        #print(f"Deltas: step {self.StepDelta}, time {self.TimeDelta}")

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
            self.Logger.Warning(f"Step {self.Step} <= last step: {self.PrevStep}. Nothing to calculate.")
            return
        if Time == None:
            Time = time.time()

        if self.StartRealTime == 0:
            self.StartRealTime = Time

        #print(f"TimeDelta: {self.TimeDelta}, StepDelta: {self.StepDelta}")

        self.CurrentRealTime = Time
        self.ElapsedRealTime = self.CurrentRealTime - self.StartRealTime - self.PausedTime

        if self.Step >= 0 and self.MaxStep > 0:
            self.StepsLeft = self.MaxStep - self.Step

        if self.Time >= 0 and self.MaxTime > 0:
            self.TimeLeft = self.MaxTime - self.Time

        if self.MaxStep > 0:
            self.StepsProgress = self.Step / self.MaxStep
        if self.MaxTime > 0:
            self.TimeProgress = self.Time / self.MaxTime

        self.CalculateETA()
        if self.ElapsedRealTime > 0:
            self.CalculateAvgETA()

        self.PrevStep = self.Step
        self.PrevTime = self.Time
        self.PrevRealTime = self.CurrentRealTime

        self.StatsUpdated = True

class SimSequenceStatus:
    def Reset(self):
        self.StatsUpdated = False

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

        self.StartRealTime = 0
        self.ElapsedRealTime = 0

        self.AvgStepSpeed = 0
        self.AvgTimeSpeed = 0
        self.AvgStepPerTime = 0
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

    def Next(self):
        self.Iteration += 1
        self.PrevStep = self.Step
        self.PrevTime = self.Time
        self.PrevRealTime = self.ElapsedRealTime

    def Recalculate(self, SimStatus, MaxStep = -1, MaxTime = -1):
        self.MaxStep = MaxStep
        self.MaxTime = MaxTime

        self.StepSpeed = SimStatus.StepSpeed
        self.TimeSpeed = SimStatus.TimeSpeed

        self.StepDelta = SimStatus.StepDelta
        self.TimeDelta = SimStatus.TimeDelta
        self.RealTimeDelta = SimStatus.RealTimeDelta

        self.Step = self.PrevStep + SimStatus.Step
        self.Time = self.PrevTime + SimStatus.Time
        self.ElapsedRealTime = self.PrevRealTime + SimStatus.ElapsedRealTime

        if self.ElapsedRealTime > 0:
            self.AvgStepSpeed = self.Step / self.ElapsedRealTime
            self.AvgTimeSpeed = self.Time / self.ElapsedRealTime

        if self.Time > 0:
            self.AvgStepPerTime = self.Step / self.Time

        if self.Step > 0:
            self.AvgTimePerStep = self.Time / self.Step

        if MaxStep > 0:
            self.StepsLeft = MaxStep - self.Step
            self.StepsProgress = self.Step / MaxStep

            if SimStatus.StepSpeed > 0:
                self.StepETA = self.StepsLeft / SimStatus.StepSpeed

            if SimStatus.AvgStepSpeed > 0:
                self.AvgStepETA = self.StepsLeft / self.AvgStepSpeed

            if MaxTime < 0:
                if SimStatus.TimePerStep > 0:
                    self.EstMaxTime = self.StepsLeft * SimStatus.TimePerStep

                if self.AvgTimePerStep > 0:
                    self.AvgEstMaxTime = self.StepsLeft * self.AvgTimePerStep

        if MaxTime > 0:
            self.TimeLeft = MaxTime - self.Time
            self.TimeProgress = self.Time / MaxTime

            if SimStatus.TimeSpeed > 0:
                self.TimeETA = self.TimeLeft / SimStatus.TimeSpeed

            if self.AvgTimeSpeed > 0:
                self.AvgTimeETA = self.TimeLeft / self.AvgTimeSpeed

            if MaxStep < 0:
                if SimStatus.StepsPerTime:
                    self.EstMaxStep = self.TimeLeft * SimStatus.StepsPerTime

                if self.AvgStepPerTime:
                    self.AvgEstMaxStep = self.TimeLeft * self.AvgStepPerTime

        self.StatsUpdated = True

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
        self.UpdateInterval = self.Config.UpdateInterval
        self.SimStatus = SimulationStatus()
        self.SimSeqStatus = SimSequenceStatus()
        self.AccStats = AccStats()
        self.StorageStats = StorageStats()
        self.SystemStats = SystemStats()
        self.Control = ControlManager()
        self.EventQueue = SimpleQueue()
        self.DataInput = InputStream(Lines = True, EventQueue = self.EventQueue, Event = 1)
        self.ControlInput = InputTerminal(EventQueue = self.EventQueue, Event = 2, Interval = 0, UseBlessed = False, force_styling=True)
        self.UI = UI(self.SimStatus, self.AccStats, self.StorageStats, self.SystemStats, self.ControlInput, self.Config)
        self.UpdateTimer = Timer(self.Config.UpdateInterval)
        self.StorageTimer = Timer(self.Config.StorageInterval)
        self.DataParser = WarpxDataParser(self.SimStatus, self.Logger)
        self.PausedTime = 0

    def ResetState(self):
        self.UserBreak = False
        self.WarpxProcess = None
        self.State.Reset()
        self.SimStatus.Reset()
        self.AccStats.Reset()
        self.StorageStats.Reset()
        self.SimStatus.MaxStep = self.Config.MaxStep
        self.SimStatus.MaxTime = self.Config.MaxTime
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
        self.Control.Register(self.Config.SeqKey, self.SwitchSeq)
        self.Control.Register(self.Config.ISOKey, self.SwitchISO)
        self.Control.Register(self.Config.AvgKey, self.SwitchAvgStats)
        self.Control.Register(self.Config.RawModeKey, self.SwitchRaw)
        self.Control.Register(self.Config.NonDestructivePrintKey, self.SwitchDestrictive)
        self.Control.Register(self.Config.ProgressBarKey, self.SwitchProgressBar)
        self.Control.Register(self.Config.PauseKey, self.SwitchRunningState)

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
            self.DataInput.Interval = self.Config.UpdateInterval
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
        self.DataInput.Close()
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
        self.PausedAt = time.time()
        self.Paused = True
        self.UI.Status("Paused")

    def Resume(self):
        if self.WarpxProcess != None:
            System.ResumeProcTree(self.WarpxProcess)
        self.Pausedtime += time.time() - self.PausedAt
        self.Paused = False
        self.UI.Status()
        self.UI.Message("Resumed")

    def SwitchRunningState(self):
        if self.Paused:
            self.Resume()
        else:
            self.Pause()

    def SwitchDestrictive(self):
        self.Config.NonDestructivePrint = not self.Config.NonDestructivePrint
        if not self.Config.NonDestructivePrint:
            self.UI.First = True

    def SwitchSeq(self):
        self.SimSeq = not self.SimSeq
        if self.SimSeq:
            self.UI.SimStatus = self.SimSeqStatus
            self.UI.Message("All sequence stats")
        else:
            self.UI.SimStatus = self.SimStatus
            self.UI.Message("Current iteration stats")

        self.CalculateESA()

    def SwitchAvgStats(self):
        self.UI.Avg = not self.UI.Avg
        self.UI.Message(f"Avg: {self.UI.Avg}")

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
        self.UI.Message(msg)

    def SwitchRaw(self):
        self.Raw = not self.Raw
        if not self.Raw:
            self.UI.First = True
        self.UI.Message(f"Raw mode: {self.Raw}")

    def SwitchProgressBar(self):
        self.Config.ProgressBar = not self.Config.ProgressBar

    def DoUserBreak(self):
        self.UI.PrintLine("\n\n")
        self.Logger.Info(f"Breaking on user demand.")
        self.UserBreak = True

    def PrepareUI(self):
        self.UI.NonDestructive = self.Config.NonDestructivePrint
        self.UI.MinLen = 79
        self.UI.CacheMaxLen()
        self.UI.Setup()

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

        if self.SimSeq:
            Sim = self.SimSeqStatus
        else:
            Sim = self.SimStatus

        if Sim.StepETA > 0:
            ETA = Sim.StepETA
            if Sim.TimeETA > 0:
                ETA += Sim.TimeETA
                ETA /= 2
        else:
            ETA = Sim.TimeETA

        if Sim.AvgStepETA > 0:
            AvgETA = Sim.AvgStepETA
            if Sim.AvgTimeETA > 0:
                AvgETA += Sim.AvgTimeETA
                AvgETA /= 2
        else:
            AvgETA = Sim.AvgTimeETA

        #print(f"SimStatus.StepsLeft: {self.SimStatus.StepsLeft}, AccStats.DataStepSpeed: {self.AccStats.DataStepSpeed}")
        if Sim.StepsLeft >= 0 and self.AccStats.DataSpeedStep >= 0:
            self.AccStats.StepESA = self.AccStats.DataSize + Sim.StepsLeft * self.AccStats.DataSpeedStep

        #print(f"SimStatus.TimeETA: {self.SimStatus.TimeETA}, AccStats.DataSpeed: {self.AccStats.DataSpeed}")
        if ETA >= 0 and self.AccStats.DataSpeed >= 0:
            self.AccStats.TimeESA = self.AccStats.DataSize + ETA * self.AccStats.DataSpeed

        if Sim.StepsLeft >= 0 and self.AccStats.AvgDataSpeedStep >= 0:
            self.AccStats.AvgStepESA = self.AccStats.DataSize + Sim.StepsLeft * self.AccStats.AvgDataSpeedStep

        if AvgETA >= 0 and self.AccStats.AvgDataSpeed >= 0:
            self.AccStats.AvgTimeESA = self.AccStats.DataSize + AvgETA * self.AccStats.AvgDataSpeed

        if ETA >= 0:
            self.StorageStats.ESA = self.StorageStats.Size + self.StorageStats.Speed * ETA

        if AvgETA >= 0:
            self.StorageStats.AvgESA = self.StorageStats.Size + self.StorageStats.Speed * AvgETA

    def UpdateSystemStats(self):
        mem = pypsutil.virtual_memory()
        self.SystemStats.FreeMemory = mem.available
        try:
            st = pypsutil.disk_usage(self.Config.StoragePath)
            self.SystemStats.FreeStorage = st.free
        except FileNotFoundError:
            pass

    def Update(self, Force = False):
        if self.StorageStats.StartSize < 0:
            try:
                self.StorageStats.StartSize = System.DirSize(self.Config.StoragePath)
            except FileNotFoundError:
                self.Logger.Warning(f"'{self.Config.StoragePath}' - file not found.")

        if self.StorageTimer.Expired():
            try:
                self.StorageStats.RawSize = System.DirSize(self.Config.StoragePath)
                self.StorageStats.Recalculate(self.SimStatus.ElapsedRealTime)
                self.StorageTimer.Reset()
            except FileNotFoundError:
                pass

        if self.UpdateTimer.Expired() or Force:
            if self.SimStatus.Updated:
                self.SimStatus.Updated = False
            self.SimStatus.PausedTime = self.GetPausedTime()
            self.AccStats.Recalculate(
                    self.SimStatus.RealTimeDelta,
                    self.SimStatus.ElapsedRealTime,
                    self.SimStatus.PausedTime
                )
            self.CalculateESA()
            if self.WarpxProcess != None:
                    #print("Update proc info.")
                try:
                    self.ProcStats = System.GetProcTreeStats(self.WarpxProcess)
                except pypsutil.NoSuchProcess as e:
                    self.WarpxProcess = None
                self.AccStats.CPUStart = self.ProcStats.CrTime
                self.AccStats.CPUTime = self.ProcStats.CPU
                self.UI.ProcStats = self.ProcStats
                    #print(str(self.ProcStats))
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

        self.AccStats.DataSize += len(OutputLine)

        #print(f"Increasing data size: {AccStats.DataSize}.")

        if not self.State.ProcessWasFinding and self.WarpxProcess == None and self.Config.Source == SourceType.FILE and self.Config.PID == 0:
            Ps = System.FileUsers(self.Config.InputFile, ["w", "a"])
#            print("")
#            print(Ps)
            Me = pypsutil.Process()
            for P in Ps:
                if P != Me:
                    WarpxProcess = P
                    self.Logger.Debug(f"Detected Warpx process: {self.WarpxProcess.name()} ({WarpxProcess.pid}).")
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

        if self.SimStatus.MaxStep > 0:
            self.Config.MaxStep = self.SimStatus.MaxStep
        if self.SimStatus.MaxTime > 0:
            self.Config.MaxTime = self.SimStatus.MaxTime

        if self.SimStatus.Main == True:
            self.State.Main = True
            self.State.Header = False
            self.UI.CurrentSection = UI.Section.MAIN
        if self.SimStatus.Footer and not self.State.Footer:
            self.State.Footer = True
            self.UI.CurrentSection = UI.Section.FOOTER
            self.Logger.Debug("Footer detected.")
            if self.Config.SkipFooter:
                return 1
            time.sleep(self.Config.UpdateInterval) # Let some time to the pipe to read last of data.
            self.DataInput.Interval = 0 # Don't wait for data anymore.

        if self.SimStatus.Step > self.SimStatus.PrevStep:
            self.SimStatus.Recalculate()
            self.CallEventHandler("OnStep", self.SimStatus.Step, self.SimStatus.Time)
            self.SimSeqStatus.Recalculate(self.SimStatus, self.Config.SeqMaxStep, self.Config.SeqMaxTime)
            self.AccStats.RecalculateStep(self.SimStatus.Step, self.SimStatus.StepDelta)

        if self.SimStatus.Header or self.SimStatus.Footer:
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

        self.CloseDataStream()

        if self.Config.AbortOnExit and self.WarpxProcess != None:
            self.WarpxProcess.terminate()

        if not self.Config.Quiet:
            self.UI.WriteSummary(self.GetRunningElapsedTime())

        return self.CallEventHandler("OnFinish", self.ExitCode)

    def Run(self):
        self.SimSeqStatus.Reset()
        self.PrepareUI()
        self.RegisterActions()
        self.PrepareLogOutput()
        self.ActivateStreams()
        self.ControlInput.DisableBuffering()

        try:
            while True:
                self.ResetState()
                self.CallEventHandler("OnInit")
                self.PrepareSource()
                self.PrepareDataStream()
                self.ActivateDataStream()

                if self.WarpxProcess == None and Config.PID > 0:
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

                self.SimSeqStatus.Next()

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
