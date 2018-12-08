from pprint import pprint

from nsetools import Nse

## get all stock symbols from nse
nse = Nse()
# all_stock_quotes = nse.get_stock_codes()

# pprint(all_stock_quotes)

## Get price of a stock

q = nse.get_quote('SBIN')

pprint(q)

# q1 = nse.get_fno_lot_sizes()

# pprint(q1)
##pprint(q)
