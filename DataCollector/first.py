import fix_yahoo_finance as yf
import matplotlib.pyplot as plt

data = yf.download('AAPL', '2016-01-01', '2018-01-01')

data.Close.plot()

plt.show()
