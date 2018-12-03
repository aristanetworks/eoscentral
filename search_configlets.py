#!/usr/bin/env python
#Search for keywords in configlets in CVP
#and return the list of configlets
#
#ignore SSL errors
import urllib3
import requests
requests.packages.urllib3.disable_warnings()
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import cvp

#connect to the CVP server on localhost
server = cvp.Cvp("localhost")

#change the credentials 
username = "cvpadmin"
password = "arista"

#authentication
server.authenticate(username,password)

#Load the configlets. Note that it may take several seconds to load
configlets = server.getConfiglets()

#Ask the user to type the interested string and 
#print the list of configlets that contain that string
while True:
	search = raw_input("Config line to search: ")
	for i in configlets:
		if search in i.config:
			print i.name
