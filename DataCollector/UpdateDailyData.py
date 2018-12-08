import datetime

import mysql.connector
import quandl

from DataCollector import UpdateDailytable


def UpdateDailyDatafromQuandl():
    ## Setting quandl variables
    ## Get Quandl data
    key = 'Kz3vwnCsa4hLgneWmUtD'
    quandl.ApiConfig.api_key = 'Kz3vwnCsa4hLgneWmUtD'

    ## Create connection to database server
    mydb = mysql.connector.connect(
        host="localhost",
        user="dbaccount",
        passwd="Vaishali@123",
        database='mydatabase'
    )

    ## Create Cursor instance for the DB Operations
    mycursor = mydb.cursor()

    ## Get all daily tables
    sqlquery = '''
    SELECT table_name FROM information_schema.tables WHERE table_name like '%_daily' AND table_schema='mydatabase';
    '''

    mycursor.execute(sqlquery)

    dailytables = mycursor.fetchall()

    for dailytable in dailytables:
        print(dailytable[0])
        ## Get the latest date data from the table
        sqlquery = "SELECT max(tradedate) from {}".format(dailytable[0])
        mycursor.execute(sqlquery)
        queryresult = mycursor.fetchall()
        ## Check if the current date is latest in the database
        ## if not, query quandl for latest data
        if queryresult[0][0] < datetime.date.today():
            latestdate = (queryresult[0][0] + datetime.timedelta(days=1)).isoformat()
            todaysdate = datetime.date.today().isoformat()
            ## Get the symbol
            stock_symbol = dailytable[0].replace('_daily', '')
            print(stock_symbol)
            nsesymbol = f'NSE/{stock_symbol}'
            ## Query quandl for further data
            stockdata = quandl.get(nsesymbol, start_date=latestdate, end_date=todaysdate)
            # pprint(stockdata)
            if len(stockdata) > 0:
                UpdateDailytable.update_daily_table(stockdata, stock_symbol)
