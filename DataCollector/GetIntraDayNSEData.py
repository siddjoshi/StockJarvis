import datetime

import mysql.connector
from nsetools import Nse


def GetIntraDayDatafromNSE():
    ## Create connection to the database
    mydb = mysql.connector.connect(
        host="localhost",
        user="dbaccount",
        passwd="Vaishali@123",
        database='mydatabase'
    )

    ## Create Cursor instance for the DB Operations
    mycursor = mydb.cursor()

    ## Instantiate instance for NSE
    nse = Nse()

    ## Get All symbols from the database
    sqlquery = "SELECT symbol from nse_symbols where FnO=true"

    mycursor.execute(sqlquery)

    allsymbols = mycursor.fetchall()

    ## Iterate through symbols
    ## Get data from NSE
    for symbol in allsymbols:
        print(symbol[0])
        current_time = datetime.datetime.now()
        ## Query NSE to get data
        q = nse.get_quote(symbol[0])

        symbolfortable = symbol[0].replace('-', '_').replace('&', '')
        ## create table is not already created
        sqlquery = '''
        CREATE TABLE IF NOT EXISTS {symbl}_nse_intraday (
        id INT NOT NULL AUTO_INCREMENT,
        stock_symbol VARCHAR(255) NOT NULL,
        tradedate DATETIME NOT NULL,
        dayHigh FLOAT NULL,
        dayLow FLOAT NULL,
        DeliveryQuantity DOUBLE NULL,
        deliveryToTradedQuantity FLOAT NULL,
        lastPrice FLOAT NULL,
        series VARCHAR(45) NULL,
        totalBuyQuantity DOUBLE NULL,
        totalSellQuantity DOUBLE NULL,
        totalTradedValue DOUBLE NULL,
        totalTradedVolume DOUBLE NULL,
        PRIMARY KEY (id),
        UNIQUE INDEX id_UNIQUE (id ASC) VISIBLE
        );
        '''.format(symbl=symbolfortable)

        mycursor.execute(sqlquery)

        d = {'a': None, 'b': '12345', 'c': None}

        for k, v in q.items():
            if q[k] is None:
                q[k] = 'Null'

        ## Insert data into the table
        query = '''
        INSERT INTO {}_nse_intraday 
        (stock_symbol, tradedate, dayHigh, dayLow, DeliveryQuantity, deliveryToTradedQuantity, lastPrice, series, totalBuyQuantity, totalSellQuantity, totalTradedValue, totalTradedVolume)
         VALUES ('{}', '{}', {}, {}, {}, {}, {}, '{}', {}, {}, {}, {});
        '''.format(symbolfortable, symbol[0], current_time, q['dayHigh'], q['dayLow'], q['deliveryQuantity'],
                   q['deliveryToTradedQuantity'], q['lastPrice'], q['series'], q['totalBuyQuantity'],
                   q['totalSellQuantity'], q['totalTradedValue'], q['totalTradedVolume'])

        mycursor.execute(query)

    ## Close DB connection
    mycursor.close()
    mydb.close()
