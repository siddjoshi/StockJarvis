# from pandas-datareader import DataReader
from datetime import datetime

from pandas_datareader import data as d

# goog = data("GOOG",  "yahoo", datetime(2000,1,1), datetime(2012,1,1))

goog = d.DataReader("GOOG", "yahoo", datetime(2000, 1, 1), datetime(2012, 1, 1))
print(goog["Adj Close"])
