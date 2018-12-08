import configparser
import logging

import sendgrid
from sendgrid.helpers.mail import *


def Send_Mail(emailaddress='siddharth.joshi21@gmail.com'):
    ## Get API key from config file
    sg = sendgrid.SendGridAPIClient(api_key=getconfig('Sendgrid', 'apikey'))
    from_email = Email("Jarvis@stockjarvis.com")
    to_email = Email(emailaddress)
    subject = "Sending with SendGrid is Fun"
    content = Content("text/plain", "and easy to do anywhere, even with Python")
    mail = Mail(from_email, subject, to_email, content)
    response = sg.client.mail.send.post(request_body=mail.get())


def logtofile():
    logging.basicConfig(filename='JarvisLogs.log', level=logging.DEBUG)
    logging.debug('This message should go to the log file')
    logging.info('So should this')
    logging.warning('And this, too')


def getconfig(section, subsection):
    config = configparser.ConfigParser()
    config.read(r'D:\projects\Fin-start1\Config\config.cfg')
    return config[section][subsection]
