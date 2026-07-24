
class ControlManager:
    Keys = {}

    def Register(self, Key, Action, *args, **kargs):
        if type(Key) != str:
            raise ValueError("Key must be type of str.")
        Args = (args, kargs)
        if Key in self.Keys:
            self.Keys[Key][Action] = Args
        else:
            self.Keys[Key] = { Action: Args }

    def Dispatch(self, Key):
        if Key in self.Keys:
            for Action in self.Keys[Key]:
                Args = self.Keys[Key][Action]
                Action(*Args[0], **Args[1])
            return True
        return False


    def Unregister(self, Key, Action = None):
        if not Key in self.Keys:
            return
        if Action == None:
            self.Keys.pop(Key)
            return
        if Action in self.Keys[Key]:
            self.Keys[Key].pop(Action)
