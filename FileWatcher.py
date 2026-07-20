
# Needs "lsof" command

import subprocess

class FileWatcher:
    def __init__(self, FileName = None, Exclude = []):
        self.FileName = FileName
        self.Exclude = Exclude

    def DetectPids(self, FileName = None, Exclude = None):
        if FileName == None:
            FileName = self.FileName
        if Exclude == None:
            Exclude = self.Exclude

        output = subprocess.check_output(['lsof', '-t', FileName])
        #print("Lsof output:", output, type(output))
        pids = output.decode().split('\n')
        ret = []
        for item in pids:
            try:
                pid = int(item)
            except ValueError:
                pass
            else:
                if pid not in Exclude:
                    ret.append(pid)
        return ret

    def DetectLastPid(self, FileName = None, Exclude = None):
         pids = self.DetectPids(FileName, Exclude)
         if type(pids) == list and len(pids) > 0:
             return pids[-1]

    def DetectFirstPid(self, FileName = None, Exclude = None):
         pids = self.DetectPids(FileName, Exclude)
         if type(pids) == list and len(pids) > 0:
             return pids[0]
