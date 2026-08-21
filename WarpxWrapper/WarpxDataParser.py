
import regex

from .Config import Config, WAITINGFORDATA, HEADER, MAIN, FOOTER

class WarpxDataParser:
    ReHeadStr = "For full input parameters, see the file\\:"
    Re1     = regex.compile("TIME")
#    Re2     = regex.compile("Evolve time")
    ReHead  = regex.compile(ReHeadStr)
    ReFoot  = regex.compile("Total Time")
    ReAbort = regex.compile("MPI_ABORT")
    ReNum   = regex.compile("[+-]?(?:[0-9]+(?:\\.[0-9]+)?|\\.[0-9]+)(?:[eE][+-]?[0-9]+)?")

    def __init__(self, Logger):
        self.Logger = Logger

    def ParseUsedInput(self, fname):
        try:
            f = open(fname, "r")
        except:
            self.Logger.Warning(f"Cannot open used input file: '{fname}'")
            return

        line = ""
        ReMaxStep = regex.compile("max_step = ")
        ReStopTime = regex.compile("stop_time = ")
        while 1:
            line = f.readline()
            if line == "":
                break
            if ReMaxStep.search(line):
                nums = self.ReNum.findall(line)
                try:
                    Config.MaxStep = int(nums[len(nums) - 1])
                except Exception as e:
                    self.Logger.ExceptWarn(e)
            if ReStopTime.search(line):
                nums = self.ReNum.findall(line)
                try:
                    Config.MaxTime = float(nums[len(nums) - 1])
                except Exception as e:
                    self.Logger.ExceptWarn(e)

    def ParseLine(self, Line):
        if not Config.State.Section == FOOTER and self.Re1.search(Line):
            if Config.State.Section == HEADER:
                Config.State.Section = MAIN
                Config.State.SectionChanged = True

            nums = self.ReNum.findall(Line)

            Config.State.Step = int(nums[0])
            Config.State.Time = float(nums[1])
            Config.State.TimeDelta = float(nums[2])
            Config.State.ProgressChanged = True

        elif Config.State.Section == HEADER and self.ReHead.match(Line):
            Config.State.Section = MAIN
            Config.State.SectionChanged = True
            PrefixLen = len(self.ReHeadStr)
            self.ParseUsedInput(Line[PrefixLen:len(Line) - 1])

        elif Config.State.Section == MAIN and self.ReFoot.match(Line):
            Config.State.Section = FOOTER
            Config.State.SectionChanged = True
        elif self.ReAbort.match(Line):
            return 2

        return 0
