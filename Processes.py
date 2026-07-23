
import psutil
import os

def PauseTree(Process):
    Ps = Process.Children(True)
    Process.suspend()
    for P in PS:
        P.suspend()

def ResumeTree(Process):
    Ps = Process.Children(True)
    Process.resume()
    for P in PS:
        P.resume()

def FileUsers(Path, Modes = None):
    Path = os.path.abspath(Path)
    Ret = []
    psutil.process_iter.cache_clear()
    for P in psutil.process_iter(["open_files"]):
        try:
            for OF in P.open_files():
                if OF["path"] == Path:
                    if "mode" in OF:
                        if Modes == None:
                            Ret.append(P)
                        else:
                            if Modes == str:
                                if OF["mode"] == Modes:
                                    Ret.append(P)
                            elif OF["Mode"] in Modes:
                                Ret.append(P)
                    else:
                        Ret.append(P)
        except:
            pass

    return Ret

