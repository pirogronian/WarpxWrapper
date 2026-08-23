
from .Various import NaN, INF, Div

class LinearExtrapolator:
    def Reset(self, BaseValue = 0, BaseDomain = 0):
        self.BaseValue = BaseValue
        self.BaseDomain = BaseDomain
        self.Value = 0
        self.PrevValue = NaN
        self.Domain = 0
        self.PrevDomain = NaN
        self.ValueDelta = NaN
        self.DomainDelta = NaN
        self.Speed = 0
        self.ValueLeft = NaN
        self.DomainLeft = INF
        self.MaxDomain = INF
        self.MaxValue = INF

    def SetSpeed(self, Speed):
        self.Speed = Speed
        self.MaxValue = self.Value + self.Speed * self.DomainLeft
        self.ValueLeft = self.MaxValue - self.Value

    def SetDeltas(self, ValueDelta, DomainDelta):
        self.ValueDelta = ValueDelta
        self.DomainDelta = DomainDelta
        self.SetSpeed(Div(ValueDelta, DomainDelta))

    def SetValue(self, Value, PrevValue = None):
        if PrevValue == None:
            self.PrevValue = self.Value
        else:
            self.PrevValue = PrevValue
        self.Value = Value - self.BaseValue

    def SetDomain(self, Domain, PrevDomain = None):
        if PrevDomain == None:
            self.PrevDomain = self.Domain
        else:
            self.PrevDomain = PrevDomain
        self.Domain = Domain - self.BaseDomain

    def AddValue(self, Value):
        self.SetValue(self.Value + Value)

    def AddDomain(self, Domain):
        self.SetDomain(self.Domain + Domain)

    def SetValues(self, Value, Domain, PrevValue = None, PrevDomain = None, Evaluate = True):
        if Value != None:
            self.SetValue(Value, PrevValue)
        if Domain != None:
            self.SetDomain(Domain, PrevDomain)
        self.DomainLeft = self.MaxDomain - self.Domain
        if not Evaluate:
            return
        self.SetDeltas(self.Value - self.PrevValue, self.Domain - self.PrevDomain)

    def GetProgress(self):
        return Div(self.Domain, self.MaxDomain)
