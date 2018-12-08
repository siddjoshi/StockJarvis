## Alpha vintage key - YHHDEI6V2I9H30L1
## EJ69MPM068NGTJ30 - somone else's key

from alpha_vantage.timeseries import TimeSeries

mykey = 'YHHDEI6V2I9H30L1'
ts = TimeSeries(key=mykey, output_format='pandas')
data, meta_data = ts.get_intraday(symbol='NSE:SBIN', interval='1day', outputsize='compact')

data1 = ts.get_daily(symbol='nse:SBIN', outputsize='full')
print(data.head())
