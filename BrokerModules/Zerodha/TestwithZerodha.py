import configparser
import logging

from kiteconnect import KiteConnect

config = configparser.ConfigParser()
logging.basicConfig(level=logging.DEBUG)

## KiteConnect API key
api_key = config['Zerodha']['api_key']
kite = KiteConnect(api_key=api_key)

print("Hello World")
