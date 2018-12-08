from pprint import pprint

import quandl

## My API key - Kz3vwnCsa4hLgneWmUtD

key = 'Kz3vwnCsa4hLgneWmUtD'
quandl.ApiConfig.api_key = 'Kz3vwnCsa4hLgneWmUtD'
# data = quandl.get("NSE/SBIN", start_date="2016-01-01", end_date="2018-01-01", api_key= key)

data = quandl.get('NSE/SBIN')
# data.Close.plot()

data1 = quandl.get('NSE/TATASTEEL', type='raw')

pprint(data1)

# data
# plt.show()
