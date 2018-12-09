Backtester is responsible for 

	- Run each and every strategy on each and every stock 
	- Log the results
	- Generate detailed backtesting report 

Backtester will also identify the time sensitivity of the strategy 
	- Time sensitivity identifies how important it is for strategy to get executed fast 

Backtester will run strategy on various combinations , 
	- generate html report for each of the backtest
	- Log the result in the database 


Backtester signals will be queued in a pipeline
