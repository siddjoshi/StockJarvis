import math

import mysql.connector


def update_daily_table(stockdata, symbol):
    totalsize = stockdata.index.size
    nsesymbol = f'NSE/{symbol}'

    ## Create connection to database server
    mydb = mysql.connector.connect(
        host="localhost",
        user="dbaccount",
        passwd="Vaishali@123",
        database='mydatabase'
    )

    ## Create Cursor instance for the DB Operations
    mycursor = mydb.cursor()
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
        Turnover = stockdata[tradedate:tradedate].Turnover_Lacs.item()

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
