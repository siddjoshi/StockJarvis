# import way2sms
from Common import W2SMS2, CommonTasks

## read from config file
username = CommonTasks.getconfig('W2SMS', 'username')
password = CommonTasks.getconfig('W2SMS', 'password')

q = W2SMS2.Sms(username, password)

mobile_number = ''

q.send(mobile_number, 'this is test message')
