
import psutil
import os

def PauseTree(Process):
    Ps = Process.children(True)
    Process.suspend()
    for P in Ps:
        P.suspend()

def ResumeTree(Process):
    Ps = Process.children(True)
    Process.resume()
    for P in Ps:
        P.resume()

def FileUsers(Path, Modes = None):
    Path = os.path.abspath(Path)
#    print("Find users of: ", Path)
    Ret = []
    psutil.process_iter.cache_clear()
    for P in psutil.process_iter():
        #print("Scanning", P.name(), P.pid)
        try:
#            p = False
#            print("Scanning", P.name(), P.pid())
            if P.name() == "WarpxWrapper":
                p = True
            print(P.open_files())
            for OF in P.open_files():
#                if p:
#                    print("Scanning open file:")
                #print(type(OF))
#                    print(OF.path, type(OF.path))
#                print(OF["path"], type(OF["path"]))
                if OF.path == Path:
#                    print("Found matching path in ", P.name(), P.pid)
                    if OF.mode != None:
                        if Modes == None:
                            Ret.append(P)
                        else:
                            if Modes == str:
                                if OF.mode == Modes:
                                    Ret.append(P)
                            elif OF.mode in Modes:
                                Ret.append(P)
                    else:
                        Ret.append(P)
#                else:
#                    if p:
#                        print(OF.path, " =/= ", Path, ">>")
        except:
            #print("Cannot scan ", P)
            pass

    return Ret

