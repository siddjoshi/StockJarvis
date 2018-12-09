This module will facilitate all communication with the broker

Major tasks will be 

	- Get balance in the account 
	- Place Limit Order  
	- Place market order
	- Place stop loss order
	- Get details for current positions
	- Get live market data
	- Get reports (Optional)

This module will support plug-in model so there can be separate plug-in for any broker we want to add to the system


It will get unparsed messages from the webserver , which they received from the Broker 

Broker module has to parse the information and communicate that back to Controller for action/update