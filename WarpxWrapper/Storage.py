
import os

def DirSize(Path):
    Ret = 0
    for Dirpath, Dirnames, Filenames in os.walk(Path):
        for F in Filenames:
            FP = os.path.join(Dirpath, F)
            # skip if it is symbolic link
            if not os.path.islink(FP):
                Ret += os.path.getsize(FP)

    return Ret
