import csv
import datetime
import os
from os import walk

import mysql.connector

## Create connection to database server
mydb = mysql.connector.connect(
    host="localhost",
    user="dbaccount",
    passwd="Vaishali@123",
    database='mydatabase'
)

mycursor = mydb.cursor()

mypath = r"D:\TradeData\Pending import\NSE 2013-2014\NSE 2014\CSV"
f = []
for (dirpath, dirnames, filenames) in walk(mypath):
    f.extend(filenames)
    break

for i in range(0, len(f)):
    if ".rar" not in f[i]:
        csvfilepath = mypath + "\\" + f[i]
        with open(csvfilepath) as csvfile:
            readCSV = csv.reader(csvfile, delimiter=',')
            for row in readCSV:
                # print(row)
                if row[0] != 'Ticker':
                    ## Add to mysql
                    sql = """
                    INSERT INTO stocks_fno1_1min (Ticker, Date, Time, Open, High, Low, Close, Volume, `Open Interest`)
                    VALUES ('{}', '{}', '{}', {}, {}, {}, {}, {}, {});
                    """.format(row[0], (datetime.datetime.strptime(row[1], "%d/%m/%Y")), row[2], row[3], row[4], row[5],
                               row[6], row[7], row[8])
                    ## Removed parse(row[1].date())

                    mycursor.execute(sql)
        mydb.commit()
        donecsvfilepath = csvfilepath + ".done"
        os.rename(csvfilepath, donecsvfilepath)

mycursor.close()
mydb.close()
