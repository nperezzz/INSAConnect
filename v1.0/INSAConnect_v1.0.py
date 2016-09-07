#!/usr/bin/env python
# -*- coding: utf-8 -*-

''' 
  ___ _   _ ____    _    ____                            _           _   ___  
 |_ _| \ | / ___|  / \  / ___|___  _ __  _ __   ___  ___| |_  __   _/ | / _ \ 
  | ||  \| \___ \ / _ \| |   / _ \| '_ \| '_ \ / _ \/ __| __| \ \ / / || | | |
  | || |\  |___) / ___ \ |__| (_) | | | | | | |  __/ (__| |_   \ V /| || |_| |
 |___|_| \_|____/_/   \_\____\___/|_| |_|_| |_|\___|\___|\__|   \_/ |_(_)___/ 
                                                                              

    This program is intended for use by INSA Toulouse students living on campus. Other people who have a captive portal problem may find interest in reusing this as well.

    Our school has set up a captive portal, which has quickly become infamous, since you get disconnected every 6 hours and everything stops working until you reconnect manually. Obviously, the points in time where you get disconnected are always subject to the full beauty of Murphy's law.

    Before this, other students have put together various respectable solutions of their own, most notably:
        - A MAC OS program by Arthur Papailhau, INSA Toulouse (https://github.com/papay0/INSAConnect)
        - A Google Chrome extension by Rémi Prévost, INSA Toulouse (https://github.com/RemiPrevost/INSAConnect)
        - An Android app by Vadim Caen, INSA Lyon (https://github.com/vcaen/InsaAutoConnect)
        - An unreliable solution for Windows that uses CURL and the Windows Task Scheduler (made by someone from the Maths department ;))
    However, there was no native and truly convenient solution for Windows and Linux.

    This lightweight program automatically connects/reconnects you to the internet via the captive portal in any situation, and usually does it in less than a second. It works on Windows and Linux. It may work on MAC OS, but I have not tested that.
    At any time, the program knows whether you are connected behind the captive portal, connected through the captive portal, connected from the exterior, or not connected to the internet. If you are connected through the captive portal, it knows when your current session expires and renews it just before it expires. When you come back to your dorm, it logs in as soon as your computer is connected to your wifi. After using this program for a week, I forgot that the captive portal even existed.

    This version is specific to our school's captive portal, but it was designed to be very easily adapted to automatically connect to any captive portal. You may only need to change ConnectionManager's connect() and disconnect() functions, and the INI file. 
'''

import re
import time
import datetime
import socket
import sys
import os
import platform
from multiprocessing import Process
from threading import Thread
from functools import partial
import pickle

import tempfile
import configparser
import requests
from pydispatch import dispatcher

from getch import getch

__author__ = "Nicolas Perez"
__copyright__ = "Copyright 2016"
__license__ = "GPL"
__version__ = "1.0"
__email__ = "hi@nicolasperez.com"
__state__ = "Production"


class ConnectionModel:

    def __init__(self):
        self.INI_FILE_NAME = 'INSAConnect.ini'
        self.DAT_FILE_NAME = 'INSAConnectSession.dat'
        
        self._init_from_config_file()
        self.currentSession = {'captive_portal': None, 'ID': None, 'end_timestamp': float('inf'), 'end_time': float('inf')}
        self._read_session_dat_file()
        self.connectionStateText = "Bonjour !\n\nVérification de l'état de la connexion..."
        self.connectedThroughCaptivePortal = False

        self._connectionStateCounter = 0

    def _init_from_config_file(self):
        """Reads the parameters from the config file."""
        config = configparser.SafeConfigParser()
        try:
            config.read(self.INI_FILE_NAME)
            self.LOGIN = config['DEFAULT']['login']
            self.PASSWORD = config['DEFAULT']['pass']
            self.CAPTIVE_PORTALS = {}
            for captive_portal in [c.split(':')[-1] for c in config.sections() if c.startswith('Captive_portal:')]:
                self.CAPTIVE_PORTALS[captive_portal] = dict(URL = config['Captive_portal:'+captive_portal]['url'],
                                                            DOMAIN = config['Captive_portal:'+captive_portal]['domain'],
                                                            PORT = int(config['Captive_portal:'+captive_portal]['port']),
                                                            TIMEOUT = int(config['Captive_portal:'+captive_portal]['timeout']))
        except:
            input('ERREUR: Le fichier INI est mal formé ou inexistant.')
            raise

    def _write_session_dat_file(self):
        """Stores the session's info in a file so that the program can remember it if the user restarts the program or reboots their computer."""
        with open(os.path.join(tempfile.gettempdir(), self.DAT_FILE_NAME), 'wb') as file:
            pickler = pickle.Pickler(file)
            pickler.dump(self.currentSession)

    def _read_session_dat_file(self):
        try:
            with open(os.path.join(tempfile.gettempdir(), self.DAT_FILE_NAME), 'rb') as file:
                unpickler = pickle.Unpickler(file)
                unpickledSession = unpickler.load()
                if (unpickledSession['captive_portal'] == self.currentSession['captive_portal'] and unpickledSession['end_timestamp'] > time.time()):
                    self.currentSession = unpickledSession
        except:
            pass

    def setConnectionStateText(self, text):
        """Changes the text that describes the connection's state in the model and informs the view."""
        if self.connectionStateText != text and self._connectionStateCounter >= 0: #XXX
            self.connectionStateText = text
            #Prévient la vue que le texte a changé
            dispatcher.send(signal='view_display_update', sender=self)
            self._connectionStateCounter = 0
        else:
            self._connectionStateCounter += 1

    def getCurrentSession(self):
        self._read_session_dat_file()
        return self.currentSession

    def setCurrentSession(self, captive_portal, currentSessionID):
        """Saves data about the current session in a variable and in a file."""
        if currentSessionID != self.getCurrentSession()['ID']:
            self.currentSession['captive_portal'] = captive_portal
            self.currentSession['ID'] = currentSessionID
            self.currentSession['end_timestamp'] = time.time() + self.CAPTIVE_PORTALS[captive_portal]['TIMEOUT']
            self.currentSession['end_time'] = datetime.datetime.fromtimestamp(self.currentSession['end_timestamp']).strftime('%H:%M')
            self._write_session_dat_file()

    def setConnectedThroughCaptivePortal(self, connectedThroughCaptivePortal):
        """Just sets that value so the view knows what to display."""
        if self.connectedThroughCaptivePortal != connectedThroughCaptivePortal:
            self.connectedThroughCaptivePortal = connectedThroughCaptivePortal
            dispatcher.send(signal='view_display_update', sender=self)


class ConnectionManager:

    def __init__(self):
        self.model = ConnectionModel()
        self.view = ConnectionView(self.model, self)
        self.currentCaptivePortal = None

        self.thread = None
        self.monitorConnectionState = True
        self.autoManageConnection = True
        self.shouldVerifySession = True
        
    def _internet(self, host='google.com', port=80, timeout=3):
        """Checks internet and DNS connectivity."""
        try:
            socket.setdefaulttimeout(timeout)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
            return True
        except Exception:
            return False

    def _detect_captive_portal(self):
        """Checks whether or not we see one of the captive portals from where we're connected."""
        for captive_portal in self.model.CAPTIVE_PORTALS.keys():
            if self._internet(host=self.model.CAPTIVE_PORTALS[captive_portal]['DOMAIN'], port=self.model.CAPTIVE_PORTALS[captive_portal]['PORT']):
                self.model.currentSession['captive_portal'] = captive_portal
                return captive_portal
        return None

    def _ping(self, host='8.8.8.8'):
        """Returns True if host responds to a ping request (works on Windows and Linux)."""
        if platform.system().lower() == "windows":
            pingCMD = "ping -n 1 -w 1000 "+host+" > NUL"
        else:
            pingCMD = "ping -c 1 -W 1 "+host+" > /dev/null"
        return os.system(pingCMD) == 0

    def connect(self):
        """Logs in on the captive portal to get access to the interwebz."""
        try:
            login_data = {'auth_user': self.model.LOGIN,
                          'auth_pass': self.model.PASSWORD,
                          'accept': 'Connexion'}
            r = requests.post(self.model.CAPTIVE_PORTALS[self.currentCaptivePortal]['URL'], data=login_data)
            if 'erreur' in r.text:
                self.model.setConnectionStateText("Erreur d'authentification sur le portail captif.\nVeuillez vérifier vos identifiants dans le fichier\nINSAConnect.ini.")
            else:
                sessionID = str(re.search('<input name="logout_id" type="hidden" value="(.*)" />', r.text).group(1))
                self.model.setCurrentSession(self.currentCaptivePortal, sessionID)
        except: #(KeyError, )
            pass

    def disconnect(self):
        """Logs out from the captive portal (before it logs you out)."""
        self.connect()
        logout_data = {'logout_id': self.model.currentSession['ID']}
        try:
            logout_data['logout_id'] = self.model.currentSession['ID']
            r = requests.post(self.model.CAPTIVE_PORTALS[self.currentCaptivePortal]['URL'], data=logout_data)
        except:
            pass

    def reconnect(self):
        """Logs out from the captive portal and immediately back in to renew the session."""
        self.disconnect()
        self.connect()

    def run(self, parent):
        """Monitors the connection's state and automatically connects/reconnects to the captive portal when required."""
        self = parent
        while self.monitorConnectionState:
            try:
                self.currentCaptivePortal = self._detect_captive_portal()
                if self.currentCaptivePortal is None:
                    if self._internet():
                        self.model.setConnectionStateText("Vous êtes connecté à internet depuis l'extérieur.")
                    else:
                        self.model.setConnectionStateText("Vous n'êtes pas connecté à internet.")
                    self.model.setConnectedThroughCaptivePortal(False) #Utile pour que la vue soit au courant de l'état de la connexion
                    self.shouldVerifySession = True
                elif self.currentCaptivePortal and not self._ping():
                    self.model.setConnectionStateText("Vous êtes sur le réseau "+str(self.model.getCurrentSession()['captive_portal'])
                                                      +"\n(non-connecté au portail captif)"
                                                      +("\nConnexion en cours..." if self.autoManageConnection else ""))
                    self.model.setConnectedThroughCaptivePortal(False)
                    self.shouldVerifySession = True
                    if self.autoManageConnection: 
                        self.connect()
                else:
                    if not self.model.getCurrentSession()['ID']:
                            self.connect()
                    elif self.shouldVerifySession:
                        self.connect()
                        self.shouldVerifySession = False
                    self.model.setConnectionStateText("Vous êtes connecté à internet depuis le réseau : \n"
                                                      +str(self.model.getCurrentSession()['captive_portal'])
                                                      +"\nVotre session ("+str(self.model.getCurrentSession()['ID'])+") expire à "+str(self.model.getCurrentSession()['end_time']))
                    self.model.setConnectedThroughCaptivePortal(True) #Utile pour que la vue soit au courant de l'état de la connexion
                    if self.autoManageConnection and self.model.getCurrentSession()['end_timestamp'] - time.time() < 60:
                        self.model.setConnectionStateText("Reconnexion automatique en cours...")
                        self.reconnect()
                time.sleep(1)
            except (KeyboardInterrupt, SystemExit):
                break

    def start_monitoring(self):
        """Activates connection state monitoring."""
        self.monitorConnectionState = True
        if not self.thread:
            self.thread = Thread(target=self.run, args=(self,))
            self.thread.daemon = True
            self.thread.start()

    def _stop_monitoring(self):
        """Deactivates connection state monitoring. This function is not really supposed to be called at any point."""
        self.monitorConnectionState = False
        if self.thread:
            self.thread.join()
            self.thread = None

    def setAutoConnectionManagement(self, bool_=None):
        """Toggles/sets automatic reconnection when the computer is disconnected from the captive portal or the session is close to expiration."""
        if bool_ is not None:
            self.autoManageConnection = bool_
        elif self.autoManageConnection:
            self.autoManageConnection = False
        else:
            self.autoManageConnection = True
        dispatcher.send(signal='view_display_update', sender=self)


class ConnectionView:

    def __init__(self, model, controller):
        self.model = model
        self.controller = controller
        self.TERM_WIDTH = 55
        self.TERM_HEIGHT = 27
        self.activeCommands = []
        dispatcher.connect(self.display_update, signal='view_display_update', sender=dispatcher.Any)

    def _prepare_console(self):
        """Adjusts the console window's look.'"""
        if platform.system().lower() == "windows":
            _ = os.system('mode con: cols='+str(self.TERM_WIDTH)+' lines='+str(self.TERM_HEIGHT))
            _ = os.system('color F0')
            _ = os.system('title INSAConnect')
        else:
            self._clear()
            print('\033[8;'+str(self.TERM_HEIGHT)+';'+str(self.TERM_WIDTH)+'t')

    def _clear(self):
        """Clears the text in the terminal (works on Windows and Linux)."""
        if platform.system().lower() == "windows":
            _ = os.system('cls')
        else:
            print('\x1b[H\x1b[2J')

    def _printConnectionStateText(self):
        """Prints the connection state text. Makes it centered and adds separators above and below."""
        separator = self._centerline("-"*33) + "\n"
        text = self.model.connectionStateText
        print(separator)
        for line in text.split('\n'):
            print(self._centerline(line))
        print("\n" + separator)

    def _centerline(self, line):
        """Centers a line of text in the terminal (provided its length is lower than the terminal's width)."""
        return " "*int((self.TERM_WIDTH-len(line))/2) + line

    def _displayMenu(self):
        """Dynamically displays the menu and sets which commands are active."""
        noInternetConnection = not self.model.connectedThroughCaptivePortal and not self.controller.currentCaptivePortal
        menu = []
        if not noInternetConnection:
            menu.append(" d: Déconnexion" if self.model.connectedThroughCaptivePortal else " c: Connexion")
            menu.append(" r: Reconnexion" if self.model.connectedThroughCaptivePortal else "")
        menu.append(" t: Désactiver la reconnexion automatique" if self.controller.autoManageConnection else " t: Activer la reconnexion automatique")
        self.activeCommands = [c[1] for c in [el for el in menu if len(el) > 2]]
        for choice in menu:
            print(choice)

    def display_update(self, sender):
        """Just updates the view"""
        self._display()

    def _display(self, messageTemporaire="", menu=True):
        """Displays/refreshes the view as text in the console."""
        self._clear()
        print("\n"*4)
        print(self._centerline("   ___ _   _ ____    _ ***                   \n")+
              self._centerline("  |_ _| \ | / ___|  / \ ** INSTITUT NATIONAL \n")+
              self._centerline("   | ||  \| \___ \ / _ \ * DES SCIENCES      \n")+
              self._centerline("   | || |\  |___) / ___ \  APPLIQUEES        \n")+
              self._centerline("  |___|_| \_|____/_/   \_\ TOULOUSE          \n")+
              self._centerline("                                             \n"))
        print("\n")
        self._printConnectionStateText()
        print("\n"*2)
        if menu:
            self._displayMenu()
        elif not messageTemporaire:
            print("\n"*2)
        if messageTemporaire:
            print(messageTemporaire)

    def run(self):
        """This is the function you need to call to run the view indefinitely."""
        self._prepare_console()
        self._display(menu=False)
        self._listen_input()

    def _listen_input(self):
        """Indefinitely listens to the user's char input and reacts accordingly.
            Commands that are not displayed on the menu are deactivated.
        """
        while True:
            try:                
                inputKey = getch().lower()
                menuCommands = {'c': (self.controller.connect, " Connexion..."),
                                'd': (self.controller.disconnect, " Déconnexion..."),
                                'r': (self.controller.reconnect, " Reconnexion..."),
                                't': ((self.controller.setAutoConnectionManagement, " Reconnexion automatique désactivée.") if self.controller.autoManageConnection
                                       else (self.controller.setAutoConnectionManagement, " Reconnexion automatique activée."))}

                if inputKey in menuCommands.keys() and inputKey not in self.activeCommands:
                    inputCommand = (lambda: None, " Commande indisponible.")
                else:
                    menuCommands = {k: v for (k,v) in menuCommands.items() if k in self.activeCommands}
                    inputCommand = menuCommands.get(inputKey, (lambda: None, " Commande non-supportée."))
                justDisplayMessage = inputKey == 't' or inputKey not in menuCommands.keys() or inputKey not in self.activeCommands

                self._display(messageTemporaire=inputCommand[1]+"\n"*2, menu=False)
                if justDisplayMessage:
                    time.sleep(0.5)
                inputCommand[0]()
                if justDisplayMessage:
                    self._display()
                else:
                    self._display(messageTemporaire=inputCommand[1]+"\n"*2, menu=False)
            except (KeyboardInterrupt, SystemExit):
                break


if __name__ == "__main__":
    cm = ConnectionManager()
    cm.start_monitoring()
    cm.view.run()
