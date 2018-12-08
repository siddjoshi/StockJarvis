import math

import mysql.connector
import quandl

## Create connection to database server
mydb = mysql.connector.connect(
    host="localhost",
    user="dbaccount",
    passwd="Vaishali@123",
    database='mydatabase'
)

## Create Cursor instance for the DB Operations
mycursor = mydb.cursor()

## Create database if does not exist
# mycursor.execute("CREATE DATABASE IF NOT EXISTS DailyData")

## Create database connection-
## Create DB connection
'''
mydb = mysql.connector.connect(
  host="localhost",
  user="dbaccount",
  passwd="Vaishali@123",
  database='DailyData'
)

'''

## Create Cursor instance for the DB Operations
# mycursor = mydb.cursor()


## Get Quandl data
key = 'Kz3vwnCsa4hLgneWmUtD'
quandl.ApiConfig.api_key = 'Kz3vwnCsa4hLgneWmUtD'

# data1 = quandl.get('NSE/TATASTEEL', type='raw')

## Get List of Nifty 50 Stocks
##sqlquery = "select symbol from nse_symbols where nifty50=TRUE"

## Get List of FnO Stocks
sqlquery = "select symbol from nse_symbols where nifty50=false and FnO=true"

# symbollist = []

mycursor.execute(sqlquery)

symbollist = mycursor.fetchall()

## Get existing daily tables
## If table exist, remove it from the list

sqlquery = "SELECT table_name FROM information_schema.tables where (table_name like '%_daily') AND table_schema='mydatabase' "

mycursor.execute(sqlquery)

donesymbollist = mycursor.fetchall()

donesymbollist1 = []

for d in donesymbollist:
    donesymbollist1.append((d[0].replace('_daily', '').upper(),))

for i in range(0, len(donesymbollist1)):
    if donesymbollist1[i] in symbollist:
        symbollist.remove(donesymbollist1[i])

## Iterate through nifty 50 stocks
## Get quandl data
## Save it in the database

for symbol1 in symbollist:
    ## query Quandl and get data
    symbol = symbol1[0]
    print(symbol)
    nsesymbol = f'NSE/{symbol}'
    stockdata = quandl.get(nsesymbol, type='raw')
    totalsize = stockdata.index.size

    ## Create table to store the daily data for the Stock
    sqlquery = '''CREATE TABLE IF NOT EXISTS {symb}_DAILY (
        tradedate date NOT NULL,
        nse_symbol VARCHAR(255) NOT NULL,
        OpenPrice float ,
        ClosePrice float,
        HighPrice float ,
        LowPrice float ,
        Volume bigint,
        LastPrice float,
        Turnover float,
        PRIMARY KEY (tradedate)
    )  ENGINE=INNODB;'''.format(symb=symbol)

    mycursor.execute(sqlquery)

    for i in range(0, totalsize):
        tradedate = stockdata.index[i].date().isoformat()

        ## Adding _ for whiteaspaces
        stockdata.columns = [c.replace(' ', '_') for c in stockdata.columns]
        stockdata.columns = [c.replace('(', '') for c in stockdata.columns]
        stockdata.columns = [c.replace(')', '') for c in stockdata.columns]

        Volume = stockdata[tradedate:tradedate].Total_Trade_Quantity.item()
        Open = stockdata[tradedate:tradedate].Open.item()
        High = stockdata[tradedate:tradedate].High.item()
        Close = stockdata[tradedate:tradedate].Close.item()
        LTP = stockdata[tradedate:tradedate].Last.item()
        Low = stockdata[tradedate:tradedate].Low.item()
        Turnover = stockdata[tradedate:tradedate].Turnover_Lacs.item();

        if math.isnan(Volume):
            Volume = "NULL"

        if math.isnan(Turnover):
            Turnover = "NULL"

        if math.isnan(Open):
            Open = "NULL"

        if math.isnan(LTP):
            LTP = "NULL"

        if math.isnan(Close):
            Close = "NULL"

        if math.isnan(High):
            High = "NULL"

        if math.isnan(Low):
            Low = "NULL"

        tablename = "{}_daily".format(symbol)
        ## Inserting data into the mysql table
        sqlquery1 = "INSERT INTO {} (tradedate, nse_symbol, OpenPrice, ClosePrice, HighPrice, LowPrice, Volume, LastPrice, Turnover) VALUES ('{}', '{}',{},{},{},{},{},{},{})".format(
            tablename, tradedate, symbol, Open, Close, High, Low, Volume, LTP, Turnover)

        mycursor.execute(sqlquery1)

        mydb.commit()

## Closing the database connecton
mycursor.close()
mydb.close()

## Create Table
'''

'''

# mycursor.execute(sqlquery)
# mydb.commit()

## Insert Data in Table

## Size of the returned array
# arraysize = data1.index.size


'''
for d in all_stock_quotes.keys():
    company_name = all_stock_quotes.get(d)
    query = "INSERT INTO NSE_SYMBOLS (symbol, company_name) VALUES (%s, %s);"
    mycursor.execute(query, (d, company_name))

mydb.commit()


'''
