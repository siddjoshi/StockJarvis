import mysql.connector

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
sql = """SELECT table_name FROM information_schema.tables WHERE table_name like '%_daily' AND table_schema='mydatabase'"""

mycursor.execute(sql)

dailytables = mycursor.fetchall()

## Create connection to database server
mydb1 = mysql.connector.connect(
    host="localhost",
    user="dbaccount",
    passwd="Vaishali@123",
    database='stockinfodb'
)

## Create Cursor instance for the DB Operations
mycursor1 = mydb1.cursor()

for dailytable in dailytables:
    print(dailytable[0])
    sqlquery = '''select * from {}'''.format(dailytable[0])
    mycursor.execute(sqlquery)
    dailydata = mycursor.fetchall()
    for d in dailydata:
        for i in range(0, len(d)):
            if d[i] is None:
                d[i] = 'Null'
        sql1 = "INSERT into nse_stock_daily (tradedate, nse_symbol, OpenPrice, ClosePrice, HighPrice, LowPrice, Volume, LastPrice, Turnover)  values ({}, '{}', {}, {}, {}, {}, {}, {}, {})".format(
            d[0], d[1], d[2], d[3], d[4], d[5], d[6], d[7], d[8])
        mycursor1.execute(sql1)
        mydb1.commit()

mycursor.close()
mydb.close()

mycursor1.close()
mydb1.close()
