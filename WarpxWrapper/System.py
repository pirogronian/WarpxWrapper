
import pypsutil
import os

def IsReadable(fname):
    return os.access(fname, os.R_OK)

def IsWritable(fname):
    return os.access(fname, os.W_OK)


def PauseProcTree(Process):
    Ps = Process.children(recursive=True)
    Process.suspend()
    for P in Ps:
        P.suspend()

def ResumeProcTree(Process):
    Ps = Process.children(recursive=True)
    Process.resume()
    for P in Ps:
        P.resume()

def FileUsers(Path, Modes = None):
    Path = os.path.abspath(Path)
#    print("Find users of: ", Path)
    Ret = []
#    pypsutil.process_iter.cache_clear()
    for P in pypsutil.process_iter():
        #print("Scanning", P.name(), P.pid)
        try:
#            p = False
#            print("Scanning", P.name(), P.pid())
#            if P.name() == "WarpxWrapper":
#                p = True
            for OF in P.iter_fds():
#                if p:
#                    print("Scanning open file:")
                #print(type(OF))
#                    print(OF.path, type(OF.path))
#                print(OF["path"], type(OF["path"]))
                if OF.path == Path:
#                    print("Found matching path in ", P.name(), P.pid)
                    if OF.open_mode != None:
                        if Modes == None:
                            Ret.append(P)
                        else:
                            if Modes == str:
                                if OF.open_mode == Modes:
                                    Ret.append(P)
                            elif OF.open_mode in Modes:
                                Ret.append(P)
                    else:
                        Ret.append(P)
        except:
            #print("Cannot scan ", P)
            pass

    return Ret

class ProcTreeStats:
    def __init__(self):
        self.ProcNum = 0
        self.ProcNames = {}
        self.CrTime = 0
        self.CPU = 0
        self.Memory = 0
        self.MemoryRatio = 0
        self.AvalMemory = 0

    def __str__(self):
        return f"TreeStats(ProcNum: {self.ProcNum}, ProcNames: {self.ProcNames})"

def GetProcTreeStats(Process):
    Stats = ProcTreeStats()
    Tree = Process.children(recursive = True)
    Tree.insert(0, Process)
    Stats.ProcNum = len(Tree)
#    print(Tree, Stats.ProcNum)
    for Proc in Tree:
        name = Proc.name()
        if name in Stats.ProcNames:
            Stats.ProcNames[name] += 1
        else:
            Stats.ProcNames[name] = 1

        Stats.CrTime += Proc.create_time()
        CpuTimes = Proc.cpu_times()
        Stats.CPU += CpuTimes.user + CpuTimes.system

        Stats.Memory += Proc.memory_info().rss
        Stats.MemoryRatio += Proc.memory_percent()

    Stats.CrTime = Stats.CrTime / len(Tree)

    return Stats

def DirSize(Path):
    Ret = 0
    for Dirpath, Dirnames, Filenames in os.walk(Path):
        for F in Filenames:
            FP = os.path.join(Dirpath, F)
            # skip if it is symbolic link
            if not os.path.islink(FP):
                Ret += os.path.getsize(FP)

    return Ret

def ClearDir(Path):
    for (root, dirs, files) in os.walk(Path):
        for f in files:
            os.unlink(root + "/" + f)

def PrepareEmptyDir(Path):
    try:
        os.mkdir(Path)
    except FileExistsError:
        ClearDir(Path)
