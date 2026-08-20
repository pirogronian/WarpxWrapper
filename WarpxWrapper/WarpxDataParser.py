
import regex

class WarpxDataParser:
    ReHeadStr = "For full input parameters, see the file\\:"
    Re1     = regex.compile("TIME")
#    Re2     = regex.compile("Evolve time")
    ReHead  = regex.compile(ReHeadStr)
    ReFoot  = regex.compile("Total Time")
    ReAbort = regex.compile("MPI_ABORT")
    ReNum   = regex.compile("[+-]?(?:[0-9]+(?:\\.[0-9]+)?|\\.[0-9]+)(?:[eE][+-]?[0-9]+)?")

    def __init__(self, SimStatus, Logger):
        self.SimStatus = SimStatus
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
                    self.SimStatus.MaxStep = int(nums[len(nums) - 1])
                except Exception as e:
                    self.Logger.ExceptWarn(e)
            if ReStopTime.search(line):
                nums = self.ReNum.findall(line)
                try:
                    self.SimStatus.MaxTime = float(nums[len(nums) - 1])
                except Exception as e:
                    self.Logger.ExceptWarn(e)

    def ParseLine(self, Line):
        if not self.SimStatus.Footer and self.Re1.search(Line):
            self.SimStatus.Header = False # Just in case we missed something
            self.SimStatus.Main = True

            nums = self.ReNum.findall(Line)

            self.SimStatus.Step = int(nums[0])
            self.SimStatus.Time = float(nums[1])
            self.SimStatus.TimeDelta = float(nums[2])

        elif self.SimStatus.Header == True and self.ReHead.match(Line):
            self.SimStatus.Header = False
            self.SimStatus.Main = True
            PrefixLen = len(self.ReHeadStr)
            self.ParseUsedInput(Line[PrefixLen:len(Line) - 1])

        elif self.SimStatus.Footer == False and self.ReFoot.match(Line):
            self.SimStatus.Main = False
            self.SimStatus.Footer = True
        elif self.ReAbort.match(Line):
            return 2

        return 0
