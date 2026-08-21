
from .Various import INF, NaN

WAITINGFORDATA = 0
HEADER = 1
MAIN = 2
FOOTER = 3

class ConfigClass:
    def ParseParam(self, Name):
        obj = self
        names = Name.split(".")
        name = None
        for vn in names:
            if name:
                obj = getattr(obj, name)
            name = vn
        return obj, name

    def GetParam(self, Name):
        return getattr(*self.ParseParam(Name))

    def SetParam(self, Name, Value):
        return setattr(*self.ParseParam(Name), Value)

    MaxParamLength = 0
    LogLevel = "info"
    Quiet = False
    ErrorIsFatal = True
    DataInterval = 0.1
    UpdateInterval = 0.5
    StorageInterval = 5.0
    DontRun = False

    LogFile = "Log"
    MaxLogSize = 0
    MaxLogFileSize = 0
    StoragePath = "diags"

    MaxStep = INF
    MaxTime = INF

    SeqMaxStep = INF
    SeqMaxTime = INF

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

    BreakKey = "Esc"
    SeqKey = 's'
    FormatKey = "f"
    NonDestructivePrintKey = "d"
    AvgKey = 'a'
    RawOutputKey = 'r'
    ProgressBarKey = 'p'
    PauseKey = ' '
    ShorterIntervalKey = 'PgUp'
    LongerIntervalKey = 'PgDn'

    class SimulationStateClass:
        def Reset(self):
            self.Step = 0
            self.Time = 0
            self.Section = WAITINGFORDATA
            self.ProgressChanged = False
            self.SectionChanged = False
            self.ProcessFinding = True

        def __init(self):
            self.Reset()

    class UIClass:
        Enabled = True
        ProgressBar = True
        NonDestructivePrint = False
        Average = False
        Sequence = False

    def __init__(self):
        self.State = self.SimulationStateClass()
        self.UI = self.UIClass()

Config = ConfigClass()
