#!/usr/bin/env python
# Copyright (c) 2018 Arista Networks, Inc.  All rights reserved.
# Arista Networks, Inc. Confidential and Proprietary.

# Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:
# * Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
# * Redistributions in binary form must reproduce the above copyright notice,  this list of conditions and the following disclaimer in the documentation 
#   and/or other materials provided with the distribution.
# * Neither the name of the Arista nor the names of its contributors may be used to endorse or promote products derived from this software without 
#   specific prior written permission.
# 
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, 
# THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS
# BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE
# GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH
# DAMAGE.

import json
from datetime import datetime
import requests
from flask import Flask, request, abort
import argparse
import sys

app = Flask(__name__)

#ask for discord webhook URL argument and exit the program if it is not given
parser = argparse.ArgumentParser()
parser.add_argument('--discordURL', required=True, help="discord webhook URL in the following format \n https://discordapp.com/api/webhooks/{webhook.id}/{webhook.token}")
if len(sys.argv) < 2:
    parser.print_help(sys.stderr)
    sys.exit(1)        
args = parser.parse_args()

discordUrl = args.discordURL

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.method == 'POST':
        print request.json
        data2 = request.get_json()
        headers = {
            "content-type": "application/json"
        }

        #in case we have multiple alerts we have to treat each of them
        for alert_id, alert in enumerate(data2['alerts']):

            if alert['status'] == 'firing':
                    event_status = 'new'
            elif alert['status'] == 'resolved':
                    event_status = 'resolved'
            if 'deviceHostname' in alert['labels']:
                    hostname = alert['labels']['deviceHostname']
            else:
                    hostname = ""
            if 'deviceId' in alert['labels']:
                    sn = alert['labels']['deviceId']
            else:
                    sn = ""
            event_type = alert['labels']['eventType']
            sev = alert['labels']['severity']
            #sev = data2['commonLabels']['severity']
            startsAt = alert['startsAt']
            date = datetime.strptime(startsAt,'%Y-%m-%dT%H:%M:%SZ')
            month = date.strftime('%b')

            #creating dictionary for discord's accepted formatting
            data3 = {}
            data3['content'] = "**1 {} events for: {} {} {}** \n Events in this group:".format(event_status,hostname, sn, event_type)

            alert_title = alert['annotations']['title']
            #setting emoji for severities
            emoji = ""
            if sev == "CRITICAL":
                emoji = ":fire:"
            elif sev == "WARNING":
                emoji = ":warning:"
            elif sev == "INFO":
                emoji = ":information_source:"
            elif sev == "ERROR":
                emoji = ":octagonal_sign:"
            #init embed
            data3["embeds"]=[]
            data3["embeds"].append({})
            data3["embeds"][alert_id]["title"] = "**[{}]** {} {}, {} ({})".format(sev, emoji, alert_title, sn, hostname)
            
            #setting the embed color to red for new alert and green for resolved alerts
            if event_status == 'new':
                    data3["embeds"][alert_id]["color"] = 12845619
            else:
                    data3["embeds"][alert_id]["color"] = 4444444

            args = {
                            'arg0': alert['annotations']['description'],
                            'arg1': date.day,
                            'arg2': month,
                            'arg3': date.year,
                            'arg4': date.hour,
                            'arg5': date.minute,
                            'arg6': date.second,
                            'arg7': alert['generatorURL']
                            }

            data3["embeds"][alert_id]["description"]= '''
            Description: {arg0}
            Started: {arg1} {arg2} {arg3} {arg4}:{arg5}:{arg6}
            Source: {arg7}'''.format(**args)

            print data3
        data5 = json.dumps(data3)
        r = requests.post(discordUrl, data=data5, headers=headers)
        return ""
    else:
        abort(400)


if __name__ == '__main__':
    app.run(host='0.0.0.0',port='5001',debug=True)
