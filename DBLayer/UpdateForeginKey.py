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

sqlquery = ''

sqlquery = '''
ALTER TABLE `mydatabase`.`acc_daily` 
ADD INDEX `nse_symbol_idx` (`nse_symbol` ASC) VISIBLE;
;
ALTER TABLE `mydatabase`.`acc_daily` 
ADD CONSTRAINT `nse_symbol`
  FOREIGN KEY (`nse_symbol`)
  REFERENCES `mydatabase`.`nse_symbols` (`symbol`)
  ON DELETE NO ACTION
  ON UPDATE CASCADE;
'''
