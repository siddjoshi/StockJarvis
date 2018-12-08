from pprint import pprint

import mysql.connector
from nsetools import Nse

## Get data for all symbols
nse = Nse()
all_stock_quotes = nse.get_stock_codes()

pprint(all_stock_quotes)

## Create DB connection
mydb = mysql.connector.connect(
    host="localhost",
    user="dbaccount",
    passwd="Vaishali@123",
    database='mydatabase'
)

mycursor = mydb.cursor()

## Create table if not already exists
## Table will have 2 columns - SYMBOL and Company Name
sql = """CREATE TABLE IF NOT EXISTS NSE_SYMBOLS (
    symbol_id INT AUTO_INCREMENT,
    symbol VARCHAR(255) NOT NULL,
    company_name varchar(255) not null,
    PRIMARY KEY (symbol_id)
)  ENGINE=INNODB;"""

mycursor.execute(sql)

## Insert data into the table

for d in all_stock_quotes.keys():
    company_name = all_stock_quotes.get(d)
    query = "INSERT INTO NSE_SYMBOLS (symbol, company_name) VALUES (%s, %s);"
    mycursor.execute(query, (d, company_name))

mydb.commit()
