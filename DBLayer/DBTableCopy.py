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

sql = """select * from nse_symbols"""

mycursor.execute(sql)

data = mycursor.fetchall()

mycursor.close()
mydb.close()

## Create connection to database server
mydb = mysql.connector.connect(
    host="localhost",
    user="dbaccount",
    passwd="Vaishali@123",
    database='stockinfodb'
)

## Create Cursor instance for the DB Operations
mycursor = mydb.cursor()

for d in data:
    sqlquery = "INSERT into nse_symbols values {}".format(d)
    mycursor.execute(sqlquery)
    mydb.commit()
