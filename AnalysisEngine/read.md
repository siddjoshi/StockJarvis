Analysis engine is the heart of the system and is mainly comprised of different scanners. 

=> Scanner will run strategies on the stocks 

=>  Only strategies with success rate of 65%+ on last 5 years of data will be considered for trade 

=>  Strategies without backtesting results will not be considered by the scanner for reala trade 

=>  Other strategies with less than 65% accuracy may run and get logged in the DB but alerts will not be sent to Controller for the trade action 

=>  Alert from each of the strategy 
	- Will get logged in the database
	- Will be sent to the Controller for decision of action (If alert is either Buy or Sell)
	
=>  Scanner will run EOD strategies at every night. (Once latest EOD data is available)


=>  Scanner will run intraday strategies during market hours 