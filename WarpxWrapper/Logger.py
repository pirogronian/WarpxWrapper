
import enum
import logging

Verbosity = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL
    }

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
    def __init__(self, name, config):
        self.Inner = logging.getLogger(name)
        self.Handler = logging.StreamHandler()
        self.Formatter = ColorfulFormatter()
        self.Handler.setFormatter(self.Formatter)
        self.Inner.addHandler(self.Handler)
        self.Inner.setLevel(logging.INFO)
        self.Config = config

    def Log(self, level, *args):
        loglevel = Verbosity[self.Config.LogLevel]
        if self.Inner.level != loglevel: # Let user for simple LogLevel = <level> to work
            self.Inner.setLevel(loglevel)
        msg = Prepare(*args)
        self.Inner.log(level, msg)

    def Debug(self, *args):
        self.Log(logging.DEBUG, *args)

    def Info(self, *args):
        self.Log(logging.INFO, *args)

    def Warning(self, *args):
        self.Log(logging.WARNING, *args)

    def Error(self, *args):
        self.Log(logging.ERROR, *args)

    def Critical(self, *args):
        self.Log(logging.CRITICAL, *args)

    def Except(self, level, *args):
#    print(level, LogLevel)
        if level >= self.Inner.level:
            msg = Prepare(args)
            self.Inner.exception(msg)

    def ExceptDebug(self, *args):
        self.Except(logging.DEBUG, *args)

    def ExceptInfo(self, *args):
        self.Except(logging.INFO, *args)

    def ExceptWarn(self, *args):
        self.Except(logging.WARNING, *args)

    def ExceptError(self, *args):
        self.Except(logging.ERROR, *args)

    def ExceptCrit(self, *args):
        self.Except(logging.CRITICAL, *args)

