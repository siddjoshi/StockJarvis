import mysql.connector
import pandas as pd
import sqlalchemy

from TechnicalIndicators import Indicators

"""
dbconn = r"mysql://dbaccount:Vaishali@123@localhost/mydatabase"

DAL()
db = DAL(dbconn)
db.define_table('acc_daily')

# db.thing.insert(name='Chair')
# query = db.thing.name.startswith('C')
# rows = db(query).select()


print("Hello")

"""

## Create connection to database server
mydb = mysql.connector.connect(
    host="localhost",
    user="dbaccount",
    passwd="Vaishali@123",
    database='mydatabase'
)

## Create Cursor instance for the DB Operations
mycursor = mydb.cursor()

engine = sqlalchemy.create_engine("mysql+pymysql://dbaccount:{}@localhost/mydatabase".format("Vaishali@123"))

connection = engine.connect()

##df = pd.read_sql_table()

df = pd.read_sql_table("acc_daily", connection)

ab = Indicators.SMA(df, 10, 'ClosePrice')

bc = Indicators.EMA(df, 5, 'ClosePrice')

print("Hello")
