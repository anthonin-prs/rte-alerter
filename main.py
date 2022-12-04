#!/usr/bin/env python3
# coding: utf8

from email import encoders
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from configparser import ConfigParser
import json, os.path, smtplib, datetime, random, base64, requests, locale

locale.setlocale(locale.LC_TIME,'')

today = datetime.date.today()

has_red = False
has_orange = False

# sandbox = False
sandbox = True

hvalue_corresp = {1:{"color":"Vert", "message":"Pas d’alerte"},\
    2:{"color":"Orange", "message":"Le système électrique se trouve dans une situation tendue. Les éco-gestes citoyens sont les bienvenus."},\
    3:{"color":"Rouge", "message":"Le système électrique se trouve dans une situation très tendue. Si nous ne baissons pas notre consommation d'électricité, des coupures ciblées sont inévitables. Adoptons tous les éco-gestes."}\
}

color_code = {
    "vert": "#79C24D",
    "orange": "#F7D668",
    "rouge": "#FA4536"
}


# Log text with [DATE - TIME] format, write it and display it if 'display = True'
def log(text, display=True, dateprint=False):
    now = datetime.datetime.now()
    current_time = now.strftime("%d/%m/%Y - %H:%M:%S")
    if dateprint:
        log_data = "["+current_time+"] "
    else:
        log_data = ""
    log_data += text
    f = open(logfile, "a+", encoding="utf-8")
    f.write(log_data+"\n")
    f.close()
    if display:
        print(log_data)


# Check if config.ini exist or leave
if os.path.exists("config.ini"):
    parser = ConfigParser()
    parser.read('config.ini')
else:
    log("Error, no config.ini found, exiting")
    exit()

# Check if configuration is full
config_tree = {'RTE_API': ["endpoint", "client_id", "client_secret"], "MAIL": ["username", "password", "server", "port", "receivers"]}

for section in config_tree:
    if parser.has_section(section) == False:
        log(" /!\\ Missing "+section+" section /!\\")
        exit()
    for i in range(len(config_tree[section])):
        if parser.has_option(section, config_tree[section][i]) == False:
            log(" /!\\ Missing "+section+":"+config_tree[section][i]+" /!\\")
            exit()
        else:
            if parser.get(section, config_tree[section][i]) == "":
                log(" /!\\ "+section+":"+config_tree[section][i]+" empty /!\\")
                exit()

# Get config.ini values
rte_endpoint = parser.get("RTE_API", "endpoint")
rte_client_id = parser.get("RTE_API", "client_id")
rte_client_secret = parser.get("RTE_API", "client_secret")

mailusername = parser.get("MAIL", "username")
mailpassword = parser.get("MAIL", "password")
mailserver = parser.get("MAIL", "server")
mailport = parser.get("MAIL", "port")
email_receivers = parser.get("MAIL", "receivers").split(", ")
emergency_email_receivers = parser.get("MAIL", "emergency_receivers").split(", ")

credentials = rte_client_id+":"+rte_client_secret
credentials_bytes = credentials.encode("ascii")
base64_bytes = base64.b64encode(credentials_bytes)
base64_credentials = base64_bytes.decode("ascii")

token_request_headers = {'Authorization' : 'Basic '+base64_credentials}
token_request = requests.get(rte_endpoint+"/token/oauth", headers=token_request_headers)
token_response = token_request.json()
rte_api_token = token_response["access_token"]



request_headers = {'Authorization' : 'Bearer '+rte_api_token}
if sandbox:
    ecowatt_request = requests.get(rte_endpoint+"/open_api/ecowatt/v4/sandbox/signals", headers=request_headers)
else:
    ecowatt_request = requests.get(rte_endpoint+"/open_api/ecowatt/v4/signals", headers=request_headers)
ecowatt_data = ecowatt_request.json()


def clean_day(date, data):
    clean_text = "\n\n"
    clean_text += "--- Météo pour le "+date+" ---\n\n"
    clean_text += "Status "+hvalue_corresp[data['overage']]['color']+" - "+data['message']+"\n\n"
    clean_text += hvalue_corresp[data['overage']]['message']+"\n\n\n"

    clean_text += "-- Détail Horaire:\n\n"
    initial = 0
    last = 1
    for hour in data['values']:
        if hour['hvalue'] != last or hour['pas'] == 23:
            last = hour['hvalue']
            clean_text +=  " • "+str(initial)+"-"+str(hour['pas'])+"h : "+str(hvalue_corresp[hour['hvalue']]['color'])+"\n"
            initial = hour['pas']

    return clean_text


def clean_day_html(date, data):
    clean_text = "\n\n"
    clean_text += "<h1 style:'display:inline;'>"+date+": "
    clean_text += "<span style='color: "+color_code[hvalue_corresp[data['overage']]['color'].lower()]+";display: inline;'>"+hvalue_corresp[data['overage']]['color']+" - "+data['message']+"</span></h1>\n"
    clean_text += "<p style='font-style: italic;'>"+hvalue_corresp[data['overage']]['message']+"</p>\n"

    clean_text += "<h3>Détail Horaire:</h3>\n"
    initial = 0
    last = 1
    clean_text += "<ul>"
    for hour in data['values']:
        if hour['hvalue'] != last or hour['pas'] == 23:
            last = hour['hvalue']
            clean_text +=  "<li>"+str(initial)+"-"+str(hour['pas'])+"h : <span style='color: "+color_code[hvalue_corresp[data['overage']]['color'].lower()]+";display: inline-block;'>"+str(hvalue_corresp[hour['hvalue']]['color'])+"</span></li>\n"
            initial = hour['pas']
    clean_text += "</ul><hr>"
    return clean_text


cleaned_data = {}
clean_text = ""
mailcontent = ""


for day in ecowatt_data['signals']:

    date_time_obj = datetime.datetime.fromisoformat(day['jour'])
    clean_date = date_time_obj.strftime('%d %b %Y')

    cleaned_data[clean_date] = {"overage":day['dvalue'], "message":day['message'], "values":day['values']}
    
    if (cleaned_data[clean_date]['overage'] == 2):
        has_orange = True

    if (cleaned_data[clean_date]['overage'] == 3):
        has_red = True

    clean_text += clean_day(clean_date, cleaned_data[clean_date])
    mailcontent += clean_day_html(clean_date, cleaned_data[clean_date])



mailcontent += "<br><br><h3>Pour plus d'informations (zones impactées, écogestes, etc..) se rendre sur <a href='https://www.monecowatt.fr'> monecowatt.fr </a><h3/>\n"
print(clean_text)


if has_orange or has_red:
    email_subject = "Alertes de coupures électriques ["+today.strftime('%d/%m/%Y')+"]"
    email_receivers = emergency_email_receivers
else:
    email_subject = "Informations sur le réseau électriques français ["+today.strftime('%d/%m/%Y')+"]"


msg = MIMEMultipart()
msg['From'] = mailusername
msg['To'] = ",".join(email_receivers)
msg['Subject'] = email_subject

msg.attach(MIMEText(mailcontent, 'html'))

mail_content = msg.as_string()

server = smtplib.SMTP(mailserver, mailport)
server.starttls()
server.login(mailusername, mailpassword)

server.sendmail(mailusername, email_receivers, mail_content)
server.quit()
