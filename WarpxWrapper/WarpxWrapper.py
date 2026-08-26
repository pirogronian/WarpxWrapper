
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
import math

from .Config import Config, WAITINGFORDATA, HEADER, MAIN, FOOTER
from WarpxWrapper import InputStream, InputTerminal, OutputStream
from WarpxWrapper import Timer
from WarpxWrapper import FormattedTime
from WarpxWrapper import System
from WarpxWrapper import ControlManager
from WarpxWrapper import UI
from WarpxWrapper import WarpxDataParser
from WarpxWrapper.LimitedBlockWriter import LimitedBlockWriter
from .Various import IterableToStr2D, INF, NaNN, NaN, CreateKeystroke, KeyName
from .LinearExtrapolator import LinearExtrapolator

def ChooseETA(ETA1, ETA2):
    if ETA1 > 0 and ETA2 > 0:
        return min(ETA1, ETA2)

    if ETA1 > 0:
        return ETA1
    return ETA2

class Stats:
    def __init__(self):
        self.RTSteps = LinearExtrapolator()
        self.RTTime = LinearExtrapolator()
        self.StepsTime = LinearExtrapolator()
        self.TimeSteps = LinearExtrapolator()

        self.DataRTime = LinearExtrapolator()
        self.DataStep = LinearExtrapolator()
        self.CPU = LinearExtrapolator()

        self.StorageSize = LinearExtrapolator()

    def Reset(self):
        self.RTSteps.Reset()
        self.RTTime.Reset()
        self.StepsTime.Reset()
        self.TimeSteps.Reset()

        self.DataRTime.Reset()
        self.DataStep.Reset()
        self.CPU.Reset()

        self.CPUStart = 0
        self.CPUTime = 0

        self.StorageSize.Reset()
        self.StorageSize.BaseValue = NaN

    def Recalculate(self, Step, MaxStep, Time, MaxTime, DataSize, CPUTime, StorageSize, RealTime,
                    PrevStep = None, PrevTime = None, PrevDataSize = None, PrevCPUTime = None, PrevStorageSize = None, PrevRealTime = None, CPUStartShift = 0):
        self.RTSteps.MaxDomain = MaxStep
        self.RTTime.MaxDomain = MaxTime

        self.StepsTime.MaxDomain = MaxTime
        self.TimeSteps.MaxDomain = MaxStep

        self.RTSteps.SetValues(RealTime, Step, PrevRealTime, PrevStep)
        self.RTTime.SetValues(RealTime, Time, PrevRealTime, PrevTime)

        self.StepsTime.SetValues(Step, Time, PrevStep, PrevTime)
        self.TimeSteps.SetValues(Time, Step, PrevTime, PrevStep)

        ETA = ChooseETA(self.RTSteps.MaxValue, self.RTTime.MaxValue)

        self.DataRTime.MaxDomain = ETA
        self.DataRTime.SetValues(DataSize, RealTime, PrevDataSize, PrevRealTime)

        self.CPU.BaseDomain = CPUStartShift
        self.CPU.SetValues(CPUTime, RealTime, PrevCPUTime, PrevRealTime)

        if NaNN(self.StorageSize.BaseValue):
            self.StorageSize.BaseValue = DataSize
        self.StorageSize.MaxDomain = ETA
        self.StorageSize.SetValues(StorageSize, RealTime, PrevStorageSize, PrevRealTime)


class SimulationStats:
    def __init__(self):
        self.Stats = Stats()
        self.AvgStats = Stats()

    def Reset(self):
        self.Step = 0
        self.Time = 0
        self.MaxStep = INF
        self.MaxTime = INF
        self.StartRealTime = -INF

        self.Stats.Reset()
        self.AvgStats.Reset()

        self.ElapsedRealTime = 0
        self.Paused = False
        self.PausedAt = 0
        self.PausedRealTime = 0
        self._PausedRealTime = 0

        self.CurrentRealTime = 0 # This is replenished automatically
        self.CPUStart = 0
        self.CPUTime = 0

        self.DataSize = 0
        self.StorageSize = NaN


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

    def SetLocalData(self):
        self.Step = Config.State.Step
        self.Time = Config.State.Time

        self.MaxStep = Config.MaxStep
        self.MaxTime = Config.MaxTime

    def Recalculate(self):
        self.SetLocalData()
        if NaNN(self.StartRealTime):
            self.StartRealTime = time.time()

        self.ElapsedRealTime = self.CompElapsedRealTime()
        self.PausedRealTime = self.CompPausedRealTime()
        self.CurrentRealTime = time.time()

        self.Stats.Recalculate(self.Step, self.MaxStep, self.Time, self.MaxTime, self.DataSize, self.CPUTime, self.StorageSize, self.CurrentRealTime)
        self.AvgStats.Recalculate(self.Step, self.MaxStep, self.Time, self.MaxTime, self.DataSize, self.CPUTime, self.StorageSize, self.ElapsedRealTime,
                                  0, 0, 0, 0, 0, 0, self.StartRealTime - self.CPUStart)


class SimSequenceStats(SimulationStats):
    def __init__(self):
        self.Current = SimulationStats()
        super().__init__()

    def Reset(self):
        self.Iteration = 0
        self.PrevStep = 0
        self.PrevTime = 0
        self.PrevRealTime = 0
        self.PrevPausedTime = 0
        super().Reset()

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

    def SetLocalData(self):
        self.Current.Recalculate()

        self.MaxStep = Config.SeqMaxStep
        self.MaxTime = Config.SeqMaxTime

        if NaNN(self.MaxStep):
            self.MaxStep = Config.MaxStep
        if NaNN(self.MaxTime):
            self.MaxTime = Config.MaxTime

        self.Step = self.PrevStep + Config.State.Step
        self.Time = self.PrevTime + Config.State.Time


class SystemStats:
    FreeMemory = 0
    FreeStorage = 0

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
        self.SimSeq = SimSequenceStats()
        self.SystemStats = SystemStats()
        self.Control = ControlManager()
        self.EventQueue = SimpleQueue()
        self.ControlInput = InputTerminal(EventQueue = self.EventQueue, Event = 2, Interval = 0, UseBlessed = False, force_styling=True)
        self.UI = UI(self.SimSeq, self.SystemStats, self.ControlInput, self.Config)
        self.UpdateTimer = Timer("UpdateInterval")
        self.StorageTimer = Timer("StorageInterval")
        self.DataParser = WarpxDataParser(self.Logger)
        self.PausedTime = 0

    def ResetState(self):
        self.UserBreak = False
        self.WarpxProcess = None
        Config.State.Reset()
        self.SimSeq.Current.Reset()
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
        BK = CreateKeystroke(Key, self.ControlInput.Terminal)
        k = Key
        if BK:
            k = KeyName(BK)
        if not self.Control.Dispatch(k):
            self.UI.Message(f"Key: {k}")
            #self.UI.Message(f"Key: {Key.encode()}")
        if not (self.UserBreak or self.Raw):
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
        self.SimSeq.Recalculate()

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
        #self.UI.PrintLine("\n\n")
        #self.Logger.Info(f"Breaking on user demand.")
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

    def UpdateStorageStats(self, Sim):
        try:
            Sim.StorageSize = System.DirSize(self.Config.StoragePath)
        except FileNotFoundError:
            if math.isnan(Sim.StorageSize):
                self.Logger.Warning(f"Storage path '{self.Config.StoragePath}' not found.")
                Sim.DataSize = INF

    def UpdateProgressUI(self):
        self.SimSeq.Recalculate()
        if not self.Raw:
            self.UI.Update()

    def Update(self, Force = False):
        if self.StorageTimer.Expired():
            self.UpdateStorageStats(self.SimSeq)
            self.UpdateStorageStats(self.SimSeq.Current)
            self.StorageTimer.Reset()

        if self.UpdateTimer.Expired() or Force:
            self.SimSeq.Recalculate()
            if self.WarpxProcess != None:
                    #print("Update proc info.")
                try:
                    self.ProcStats = System.GetProcTreeStats(self.WarpxProcess)
                except pypsutil.NoSuchProcess as e:
                    self.WarpxProcess = None
                self.SimSeq.CPUStart = self.ProcStats.CrTime
                self.SimSeq.Current.CPUStart = self.ProcStats.CrTime
                self.SimSeq.CPUTime = self.ProcStats.CPU
                self.SimSeq.Current.CPUTime = self.ProcStats.CPU
                self.UI.ProcStats = self.ProcStats
                    #print(str(self.ProcStats))
            else:
                self.UI.ProcStats = System.ProcTreeStats()
            self.UpdateSystemStats()

            self.UpdateTimer.Reset()

            if Config.State.Section == MAIN and not self.Raw:
                self.UI.Update()

    def MainLoop(self):
        self.Update()

        while not self.EventQueue.empty():
            self.EventQueue.get_nowait() # eat stalled events

        self.ProcessControlInput()

        if self.UserBreak:
            if self.StartTime < 0:
                self.StartTime = time.time()
            self.UpdateProgressUI()
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
                self.UpdateProgressUI()
                self.Logger.Debug("DataInput inactive, finishing.")
                return 1

        if Config.State.Section == WAITINGFORDATA:
            Config.State.Section = HEADER

        if self.Raw:
            print(OutputLine, end = '')

        self.SimSeq.DataSize += len(OutputLine)
        self.SimSeq.Current.DataSize += len(OutputLine)

        #print(f"Increasing data size: {AccStats.DataSize}.")

        #print(f"{not self.State.ProcessWasFinding} and {self.WarpxProcess == None} and {self.Config.Source == SourceType.FILE} and {self.Config.PID}")

        if self.StartTime < 0:
            self.StartTime = time.time()
            self.UI.PrintLine("\nGot data, starting processing.\n")

        if OutputLine \
            and Config.State.ProcessFinding \
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
            Config.State.ProcessFinding = False

        if self.LogOutput != None:
            self.LogOutput.Write(OutputLine)

        if self.DataParser.ParseLine(OutputLine) == 2:
            self.UpdateProgressUI()
            self.Logger.Warning("Warpx aborted.")
            return 2

        if Config.State.Section == FOOTER and Config.State.SectionChanged:
            self.UpdateProgressUI()
            self.Logger.Debug("Footer detected.")
            if Config.SkipFooter:
                return 1
            time.sleep(self.Config.UpdateInterval) # Let some time to the pipe to read last of data.
            self.DataInput.Interval = 0 # Don't wait for data anymore.

        if Config.State.ProgressChanged:
            #self.SimSeq.Recalculate(self.Config.SeqMaxStep, self.Config.SeqMaxTime)
            self.CallEventHandler("OnStep", Config.State.Step, Config.State.Time)

        if Config.State.Section == HEADER or Config.State.Section == FOOTER:
            print(OutputLine, end='')

        return 0

    def RunMainLoop(self):
        try:
            if self.Config.DontRun:
                self.Logger.Debug("Don't run. Exiting...")
                return 0
            while 1:
                if self.Config.SkipMain:
                    self.Logger.Debug("Skipping main.")
                    break

                self.ExitCode = self.MainLoop()
                if self.ExitCode > 0:
                    self.Logger.Debug(f"Exiting with code: {self.ExitCode}")
                    break
                Config.State.ProgressChanged = False
                Config.State.SectionChanged = False

        except Exception as e:
            self.Logger.Critical("Unhandled exception, breaking main loop.")
            self.Logger.ExceptCrit(e)
            self.ExitCode = 4

        return self.ExitCode

    def Finish(self):
        self.Resume()

        S = SourceNames[self.Config.Source]
        if (self.Config.AbortOnExit or S == SourceType.COMMAND) and self.WarpxProcess != None:
            self.Logger.Debug("Terminating WarpX.")
            self.WarpxProcess.terminate()
            time.sleep(0.1)
            self.WarpxProcess.kill()

        self.CloseDataStream()

        self.UI.WriteSummary(self.SimSeq.ElapsedRealTime)

        return self.CallEventHandler("OnFinish", self.ExitCode)

    def Run(self):
        self.ExitCode = 0
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
