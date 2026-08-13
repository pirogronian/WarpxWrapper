
import argparse
from .Various import StrToType, TypeDescription, StrToInt

class IncludeAction(argparse.Action):
    Used = False
    def __call__(self, parser, namespace, value, option_string):
        if type(value) == str:
            self.IncludeFile(value)
        else:
            for name in value:
                self.IncludeFile(name)
        self.__class__.Used = True

class ParamAction(argparse.Action):
    Param = ""
    UnpackList = False
    def __init__(self, option_strings, dest, **kwargs):
#        print("{}.__init__({}, {}, {}, {})".format(self.__class__.__name__, option_strings, dest, nargs, kwargs))
        self.Param = kwargs.pop("VarName")
        if kwargs["nargs"] == 1:
            self.UnpackList = True
        super().__init__(option_strings, dest, **kwargs)
    def __call__(self, parser, namespace, values, option_string):
        """if type(values) == list:
            print("List?", values)
            value = values[0]
        else:
            value = values"""
        value = values
        t = type(getattr(self.Config, self.Param))
        if self.UnpackList and type(value) == list:
            value = value[0]
        if type(value) != t:
            try:
                #print(f"Param value for {self.Param}: {value} ({type(value)})")
                value = StrToType(value, t)
            except:
                self.Error("Value of param {} must be convertable to {}!".format(option_string, t.__name__))
        setattr(self.Config, self.Param, value)
        self.Logger.Debug("Command line: set {} to {}".format(self.Param, value))

class ConfigManager:

    def __init__(self, Config, Logger, Error, Fatal = None, Description = None):
        self.Config = Config
        self.Logger = Logger
        self.Error = Error
        self.Fatal = Fatal
        IncludeAction.IncludeFile = self.IncludeFile
        ParamAction.Config = Config
        ParamAction.Logger = Logger
        ParamAction.Error = Error
        self.Params = []
        self.Parser = argparse.ArgumentParser(description = Description)

    def IncludeFile(self, fname):
        self.Logger.Debug(f"Including file '{fname}'.")
        try:
            f = open(fname, "r")
        except Exception as e:
            self.Logger.Error(f"Cannot open file '{fname}'.")
            self.Error(1, e)
            return
        prog = f.read()

        try:
            exec(prog, {"Config": self.Config, "StrToInt": StrToInt})
        except Exception as e:
            self.Logger.Error(f"Error while executing include file: '{fname}'")
            self.Logger.ExceptError(1, e)
            self.Error()


    def AddParam(self, VarName, *Args, **KArgs):
        v = getattr(self.Config, VarName)
        if v != None:
            if not "nargs" in KArgs:
                KArgs["nargs"] = '?' if "const" in KArgs else 1
            if not "action" in KArgs:
                KArgs["action"] = ParamAction
            if not "help" in KArgs:
                help = ""
            else:
                help = KArgs["help"]
            KArgs["help"] = f"Type: {TypeDescription(type(v), True)}. Python config variable is '{VarName}'. {help}"
            self.Parser.add_argument(*Args, VarName = VarName, **KArgs)
            self.Params.append(VarName)

            self.Config.MaxParamLength = max(self.Config.MaxParamLength, len(VarName))
        else:
            raise NameError("Variable {VarName} not found.")

    def Parse(self, Args):
        return self.Parser.parse_args(Args)
