## Class definition for signal generated from the backtester
class BTSignal:
    def __init__(self, action, stoploss, target, price=None, ordertype='Market'):
        self.action = action
        self.ordertype = ordertype
        self.stoploss = stoploss
        self.target = target
        self.price = price

