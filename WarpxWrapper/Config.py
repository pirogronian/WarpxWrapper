
class Config:
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

    MaxStep = -1
    MaxTime = -1.0

    SeqMaxStep = -1
    SeqMaxTime = -1.0

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

    BreakKey = "\x1b"
    SeqKey = 's'
    FormatKey = "f"
    NonDestructivePrintKey = "d"
    AvgKey = 'a'
    RawOutputKey = 'r'
    ProgressBarKey = 'p'
    PauseKey = ' '
    ShorterIntervalKey = '\x1b[5~'
    LongerIntervalKey = '\x1b[6~'

    class UI:
        ProgressBar = True
        NonDestructivePrint = False
        Average = False
        Sequence = False
