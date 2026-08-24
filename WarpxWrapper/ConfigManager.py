
import argparse
from .Various import StrToType, TypeDescription, StrToInt, Is, Action, kB, MB, GB, TB, kiB, MiB, GiB, TiB
from .System import PrepareEmptyDir, IncludeCurrentPath
from WarpxWrapper import Config

class IncludeAction(argparse.Action):
    Used = False
    def __call__(self, parser, namespace, value, option_string):
        if type(value) == str:
            self.IncludeFile(value)
        else:
            for name in value:
                self.IncludeFile(name)
        self.__class__.Used = True

class ExpressionAction(argparse.Action):
    def __call__(self, parser, namespace, value, option_string):
        if type(value) == str:
            self.ParamExpression(value)
        else:
            for expr in value:
                self.ParamExpression(expr)

class ParamAction(argparse.Action):
    Param = ""
    UnpackList = False
    def __init__(self, option_strings, dest, **kwargs):
        self.Param = kwargs.pop("VarName")
        if "Action" in kwargs:
            self.Action = kwargs.pop("Action")
        else:
            self.Action = None
        if kwargs["nargs"] == 1:
            self.UnpackList = True
        super().__init__(option_strings, dest, **kwargs)

    def __call__(self, parser, namespace, values, option_string):
        value = values
        t = type(Config.GetParam(self.Param))
        if self.UnpackList and type(value) == list:
            value = value[0]
        if type(value) != t:
            try:
                #print(f"Param value for {self.Param}: {value} ({type(value)})")
                value = StrToType(value, t)
            except:
                self.Error(f"Value of param {option_string} must be convertable to {t.__name__}!")
        value = Action(self.Action, value)
        Config.SetParam(self.Param, value)
        self.Logger.Debug(f"Command line: set {self.Param} to {value}")

class ConfigManager:
    RunEnv = {
        "Config": Config,
        "StrToInt": StrToInt,
        "kB": kB,
        "MB": MB,
        "GB": GB,
        "TB": TB,
        "kiB": kiB,
        "MiB": MiB,
        "GiB": GiB,
        "TiB": TiB,
        "PrepareEmptyDir": PrepareEmptyDir
        }

    def __init__(self, Logger, Error, Fatal = None, *args, **kargs):
        self.Logger = Logger
        self.Error = Error
        self.Fatal = Fatal
        IncludeAction.IncludeFile = self.IncludeFile
        ExpressionAction.ParamExpression = self.ParamExpression
        ParamAction.Logger = Logger
        ParamAction.Error = Error
        self.Params = []
        self.Parser = argparse.ArgumentParser(*args, **kargs)

    def IncludeFile(self, fname):
        self.Logger.Debug(f"Including file '{fname}'.")
        try:
            f = open(fname, "r")
        except Exception as e:
            self.Logger.Error(f"Cannot open file '{fname}'.")
            self.Error(1, e)
            return
        prog = f.read()

        IncludeCurrentPath()
        try:
            exec(prog, self.RunEnv)
        except Exception as e:
            self.Logger.Error(f"Error while executing include file: '{fname}'")
            self.Logger.ExceptError(1, e)
            self.Error()

    def ParamExpression(self, Expression):
        prog = Expression
        try:
            exec(prog, self.RunEnv)
        except Exception as e:
            self.Logger.Error(f"Error while executing expression: '{prog}'")
            self.Logger.ExceptError(1, e)
            self.Error()

    def AddParam(self, VarName, *Args, **KArgs):
        v = Config.GetParam(VarName)
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

            Config.MaxParamLength = max(Config.MaxParamLength, len(VarName))
        else:
            raise NameError(f"Variable {VarName} not found.")

    def Parse(self, Args):
        return self.Parser.parse_args(Args)
