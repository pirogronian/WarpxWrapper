
class ClearedLine:
    Extra = 0
    Len = 0
    def __init__(self, Text = ""):
        self.Set(Text)

    def Set(self, Text):
        Text = Text.rstrip()
        Len = len(Text)
        if self.Len > Len:
            self.Extra = self.Len - Len + 1
        else:
            self.Extra = 0
        self.Text = Text
        self.Len = Len

    def Append(self, Text):
        Text = Text.rstrip()
        Len = len(Text)
        self.Extra -= Len
        if self.Extra < 0:
            self.Extra = 0
        self.Text += Text
        self.Len = len(self.Text)

    def Get(self):
        return self.Text + " " * self.Extra

    def __str__(self):
        return self.Get()
