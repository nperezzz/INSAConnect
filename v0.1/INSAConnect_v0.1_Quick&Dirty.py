#!/usr/bin/env python
# -*- coding: utf-8 -*-

''' INSAConnect v0.1
Early version as a quick and dirty script. Still does the job though!
'''

import os, platform
import requests
import socket
import time
import datetime
import re

__author__ = "Nicolas Perez"
__copyright__ = "Copyright 2016"
__license__ = "GPL"
__version__ = "0.1"
__email__ = "hi@nicolasperez.com"
__status__ = "Prototype"


###############################################################################
################################# CONFIGURATION ###############################

LOGIN = 'YOUR_LOGIN_HERE'
PASSWORD = 'YOUR_PASSWORD_HERE'

CAPTIVE_PORTAL_URL = 'https://portail-promologis-lan.insa-toulouse.fr:8003/'
CAPTIVE_PORTAL_DOMAIN = 'portail-promologis-lan.insa-toulouse.fr'
CAPTIVE_PORTAL_TIMEOUT = 6*60*60

login_data = {	'auth_user': LOGIN,
				'auth_pass': PASSWORD,
				'redirurl': 'http://google.com',
				'checkbox_charte': 'on',
				'accept': 'Connexion'}
logout_data = {'logout_id': None,
				'zone': 'promologis_lan',
				'logout': 'Logout'}

###############################################################################


connection_end = float('inf')
connection_status_text = ''
compteur = 0
currentSessionID = -1

def internet(host='google.com', port=80, timeout=3):
	"""Checks internet and DNS connectivity."""
	try:
		socket.setdefaulttimeout(timeout)
		socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
		return True
	except Exception:
		return False

def captive_portal():
	"""Checks whether or not we see the captive portal from where we're connected."""
	return internet(host=CAPTIVE_PORTAL_DOMAIN, port=8003)

def ping(host='8.8.8.8'):
    """Returns True if host responds to a ping request"""
    if platform.system().lower()=="windows":
    	ping_cmd = "ping -n 1 -w 1000 "+host+" > NUL" 
    else:
    	ping_cmd = "ping -c 1 -W 1 "+host+" > /dev/null"
    return os.system(ping_cmd) == 0

def connect(url=CAPTIVE_PORTAL_URL, data=login_data):
	"""Logs in on the captive portal to get access to the interwebz."""
	try:
		r = requests.post(url, data=data)
		sessionID = str(re.search('<input name="logout_id" type="hidden" value="(.*)" />', r.text).group(1))
		logout_data['logout_id'] = sessionID
		return sessionID
	except:
		return None

def disconnect(url=CAPTIVE_PORTAL_URL, data=logout_data):
	"""Logs out from the captive portal (before it logs you out)."""
	_ = connect()
	try:
		r = requests.post(url, data=data)
	except:
		pass

def reconnect():
	"""Logs out from the captive portal and immediately back in to renew the session."""
	disconnect()
	sessionID = connect()
	return sessionID

def setConnectionStatusText(text):
	global connection_status_text
	global compteur
	if connection_status_text != text and compteur >= 1:
		connection_status_text = text
		print(datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S')+": "+connection_status_text)
		compteur = 0
	else:
		compteur += 1

while True:
	if not captive_portal():
		if internet():
			setConnectionStatusText("Vous êtes connecté à internet depuis l'extérieur du réseau INSA/promologis.")
		else:
			setConnectionStatusText("Vous n'êtes pas connecté à internet.")
		connection_end = float('inf')
	elif captive_portal() and not ping():
		setConnectionStatusText("Vous êtes sur le réseau INSA/promologis. Connexion en cours...")
		sessionID = connect()
		if ping() and sessionID != currentSessionID:
			currentSessionID = sessionID
			connection_end = time.time() + CAPTIVE_PORTAL_TIMEOUT
	else:
		connection_end_time = datetime.datetime.fromtimestamp(connection_end).strftime('%H:%M') if connection_end != float("inf") else ""
		setConnectionStatusText("Vous êtes connecté à internet depuis le réseau INSA/promologis.\nSessionID="+str(currentSessionID)+"\nVotre session expire à "+str(connection_end_time)+" (elle sera automatiquement renouvelée)") #FIXME
		if connection_end - time.time() < 60:
			setConnectionStatusText("Reconnexion automatique en cours...")
			sessionID = reconnect()
			connection_end = time.time() + CAPTIVE_PORTAL_TIMEOUT
	time.sleep(1)