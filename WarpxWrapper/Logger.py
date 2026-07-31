
import enum
import logging

class Verbosity(enum.Enum):
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL

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

def Prepare(*arg):
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

class Logger:
    def __init__(self, name):
        self.Inner = logging.getLogger(name)
        self.Handler = logging.StreamHandler()
        self.Formatter = ColorfulFormatter()
        self.Handler.setFormatter(self.Formatter)
        self.Inner.addHandler(self.Handler)
        self.Inner.setLevel(logging.INFO)
        self.Level = Verbosity.INFO

    def Log(self, level, *args):
        if self.Inner.level != self.Level.value: # Let user for simple LogLevel = <level> to work
            self.Inner.setLevel(self.Level.value)
        msg = Prepare(*args)
        self.Inner.log(level.value, msg)

    def Debug(self, *args):
        self.Log(Verbosity.DEBUG, *args)

    def Info(self, *args):
        self.Log(Verbosity.INFO, *args)

    def Warning(self, *args):
        self.Log(Verbosity.WARNING, *args)

    def Error(self, *args):
        self.Log(Verbosity.ERROR, *args)

    def Critical(self, *args):
        self.Log(Verbosity.CRITICAL, *args)

    def Except(self, level, *args):
#    print(level, LogLevel)
        if level.value >= self.Level.value:
            msg = Prepare(args)
            self.Inner.exception(msg)

    def ExceptDebug(self, *args):
        self.Except(Verbosity.DEBUG, *args)

    def ExceptInfo(self, *args):
        self.Except(Verbosity.INFO, *args)

    def ExceptWarn(self, *args):
        self.Except(Verbosity.WARNING, *args)

    def ExceptError(self, *args):
        self.Except(Verbosity.ERROR, *args)

    def ExceptCrit(self, *args):
        self.Except(Verbosity.CRITICAL, *args)

