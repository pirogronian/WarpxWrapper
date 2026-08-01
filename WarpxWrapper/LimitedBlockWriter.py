
import pathlib

class LimitedBlockWriter:
    MaxSize = 0
    BlockSize = 0
    FirstIndex = 0
    LastIndex = 0
    CurrentSize = 0
    CurrentBlockSize = 0
    FileName = "log"
    FileExt = "log"
    Flush = False
    Stream = None

    def __init__(self, MaxSize = 4096, BlockSize = 1024, FileName = "log", FileExt = "log"):
        if BlockSize > MaxSize:
            BlockSize = MaxSize
        if BlockSize == 0:
            BlockSize = MaxSize / 2
        self.MaxSize = MaxSize
        self.BlockSize = BlockSize
        self.FileName = FileName
        self.FileExt = FileExt
        self.OpenNew()

    def FilePath(self, Index):
        if self.BlockSize == 0:
            return f"{self.FileName}.{self.FileExt}"
        return f"{self.FileName}.{Index:03d}.{self.FileExt}"

    def OpenNew(self):
        path = self.FilePath(self.LastIndex)
        #print(f"Open new file: {path}")
        self.Stream = open(path, "w")
        self.LastIndex += 1

    def DeleteOldest(self):
        #print(f"Indexes: {self.FirstIndex}, {self.LastIndex}")
        path = pathlib.Path(self.FilePath(self.FirstIndex))
        #print(f"Deleting {path}")
        if path.exists():
            size = path.stat().st_size
            path.unlink()
            self.CurrentSize -= size
            self.FirstIndex += 1

    def Close(self):
        if self.Stream != None and not self.Stream.closed:
            self.Stream.close()

    def Write(self, Data):
        size = self.Stream.write(Data)
        if self.Flush:
            #print("Flushing...")
            self.Stream.flush()
        self.CurrentBlockSize += size
        if self.BlockSize > 0 and self.CurrentBlockSize > self.BlockSize:
            self.Stream.close()
            self.OpenNew()
            self.CurrentBlockSize = 0
        self.CurrentSize += size
        #print(f"{self.MaxSize} < {self.CurrentSize}?")
        if self.MaxSize > 0 and self.CurrentSize > self.MaxSize:
            self.DeleteOldest()

    def Activate(self):
        pass

    def IsActive(self):
        return True
