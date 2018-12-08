import datetime

import nsepy as np

sbin_history = np.get_history(symbol='SBIN', start=datetime.date(2018, 1, 1), end=datetime.date(2018, 11, 27))

nse_indices = np.live.NSE_INDICES

dtoi = np.live.DERIVATIVE_TO_INDEX

dqr = np.live.derivative_quote_referer

qer = np.live.quote_eq_url

ocu = np.live.option_chain_url
# pprint(sbin_history)
print('hello')
