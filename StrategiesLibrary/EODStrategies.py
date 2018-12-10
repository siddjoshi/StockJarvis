from abc import abstractmethod

from TechnicalIndicators import Indicators


class strategy:
    @abstractmethod  ## execute method will take the symbol and the data as parameter. Data will be Panda Series
    def execute(self):
        pass


class strategy1(strategy):
    def execute(self):
        print("Executing the strategy")


class strategy2(strategy):
    def __init__(self, symbol, bars, short_window=100, long_window=400):
        self.symbol = symbol
        self.data = bars
        self.short_window = short_window
        self.long_window = long_window

    def execute(self):
        print("Executing strategy 2")
        ## generate 5 days moving average
        Indicators.SMA(self.data, self.short_window, 'ClosePrice')
        ## Generate 10 days moving average
        Indicators.SMA(self.data, self.long_window, 'ClosePrice')

        ## Check when there are crossovers of 5 days SMA and 10 days SMA


## Long Hold strategies

##The rules for the Bollinger Bands would be to use a 10 day simple moving average and
##buy when the closing prices falls below the lower Band which is set at 2 standard deviations.
##The trade would be closed when the closing price breaks the upper Band.
##Trades lasted an average of 86 days.


## Based on the open interest

## Open interest up by 5%
## In first 15 days of opening up of the contract
## Analyze last 5 days trade


## test strategy


## Main Function
if __name__ == '__main__':
    s = strategy1()
    s.execute()
