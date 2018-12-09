=>  First component to start 
=>  Responsible to start other components as separate processes

=>  It will get buy or sell alerts from the scanner
=>  It will contact portfolio manager and will decide whether a position can be taken or not. 
=>  If a position has to be taken then 
	- details will be sent to broker module 
	- e-mail and sms will be sent to the user
=>  Any order placement message to Broker module will be followed by
	- Email and sms to the user 
=>  Any order confirmation, position update 

If an alert is received from EOD strategy, then most probably it is received post market hours  , in this case there will be a watch-list maintained to monitor it for next market day. So the alert will be sent to Watchlist manager


=> Get messages from broker module
	- Controller will get parsed messages from the on information received from Broker
	- Controller has to take action based on the information like
		○ Updating the positions 
		○ 
