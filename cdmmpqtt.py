#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""MPD to MQTT Connector

Usage: cdmmpqtt.py <mpd_host> <mqtt_host> <mqtt_client_name>
"""

import os
import sys
import time
import logging
import json
import paho.mqtt.client as mqtt
from uuid import getnode
from datetime import datetime
from datetime import timedelta
from mpd import MPDClient
from docopt import docopt


log = logging.getLogger(__name__)


class mpd_client():
    """
    Context manager for an MPD client connection
    """
    def __init__(self, host='localhost'):
        self.host = host
    def __enter__(self):
        self.client = MPDClient()
        self.client.timeout = 10
        self.client.connect(self.host, 6600)
        return self.client
    def __exit__(self, type, value, traceback):
        self.client.close()
        self.client.disconnect()


def mpd_status(host):
    """
    Get the current status of the MPD
    """
    result = {}
    with mpd_client(host) as client:
        result = client.status()
        result['current_song'] = client.currentsong()
        if 'title' not in result['current_song'].keys():
            result['current_song']['title'] = 'unknown'
        result['playlist'] = client.playlist()
        # 'time': '364:4535'
        elapsed = 0
        total = 0
        if 'time' in result.keys():
            (elapsed, total) = result['time'].split(':')
            result['elapsed'] = elapsed
            result['total'] = total
        else:
            result['elapsed'] = 0
            result['total'] = 0
    return result


def mqtt_connect(client, mqtt_server, mqtt_client_name, mqtt_client_password, use_tls=False):
    try:
        client.username_pw_set(mqtt_client_name, password=mqtt_client_password)
        if use_tls == True:
            pass
            #log.debug(client.tls_set(config.mqtt_server_cert, cert_reqs=ssl.CERT_OPTIONAL))
            #log.debug(client.connect(mqtt_server, port=1884))
        else:
            log.debug(client.connect(mqtt_server))
        client.subscribe("%s/open" % mqtt_client_name, 1) # level 1 means at least once
        client.on_message = on_message
    except Exception as e:
        log.debug(e)


def publish_dict(client, mqtt_client_name, name, data):
    log.debug("Publish: %s" % repr(data))
    encoded = json.dumps(data).encode('utf-8')
    client.publish('%s/%s' % (mqtt_client_name, name), encoded)


def mqtt_loop(mpd_host, mqtt_server, mqtt_client_id, mqtt_client_name, mqtt_client_password):
    global last_change
    time.sleep(2.0)
    log.info("Starting MQTT loop ...")

    # Set up the signal handler für Ctrl+C
    log.debug("MQTT loop started.")
    client = mqtt.Client(mqtt_client_id)
    mqtt_connect(client, mqtt_server=mqtt_server, mqtt_client_name=mqtt_client_name, mqtt_client_password=mqtt_client_password)
    send_discovery_msg(client, mqtt_client_name, mqtt_client_id)
    last_discovery = datetime.now()
    last_update = datetime.now() - timedelta(seconds=60)
    last_song = None

    while True:
        result = client.loop(1)
        if result != 0:
            mqtt_connect(client, mqtt_server=mqtt_server, mqtt_client_name=mqtt_client_name, mqtt_client_password=mqtt_client_password)
        time.sleep(0.5)
        # Do the actual MQTT stuff
        status = mpd_status(mpd_host)
        if (datetime.now() - last_discovery).seconds > 60:
            send_discovery_msg(client, mqtt_client_name, mqtt_client_id)
            last_discovery = datetime.now()
        if (datetime.now() - last_update).seconds > 20 or status['current_song'] != last_song:
            publish_dict(client, mqtt_client_name, 'current_song', status['current_song'])
            last_update = datetime.now()
            last_song = status['current_song']



def send_discovery_msg(client, mqtt_client_name, mqtt_client_id):
    """
    Send the discovery message, such that MsgFlo can automatically set up a component
    whenever a new instance of this program is run.

    Details, see: https://github.com/c-base/mqttwebview/issues/2
    """
    discovery_message = {
        "command": "participant",
        "protocol": "discovery",
        "payload": {
            "component": "c-base/music-player",
            "label": "c-base music player",
            "inports": [
            #     {
            #         "queue": "%s/open" % mqtt_client_name,
            #         "type": "string",
            #         "description": "URL to be opened",
            #         "id": "open",
            #     }
            ],
            "outports": [
                {
                    "queue": "%s/current_song" % mqtt_client_name,
                    "type": "object",
                    "description": "JSON object of the current song being played.",
                    "id": "current_song",
                }
            ],
            "role": "%s" % mqtt_client_name,
            "id": mqtt_client_id,
            "icon": "music"
        },
    }
    log.debug("Sending FBP discovery message.")
    client.publish('fbp', payload=json.dumps(discovery_message).encode('utf-8'), qos=0)


def on_message(client, obj, msg):
    global last_change
    payload = msg.payload.decode('utf-8')
    try:
        url = json.loads(payload)
    except:
        url = payload
    #if validators.url(url.split("#", 1)[0]):
    #    log.debug("Received message, opening %s" % url)
    #    last_change = datetime.now()
    #    open_url(url, client)
    #else:
    #    log.warning("Malformed URL received: %s" % repr(url))#


if __name__ == '__main__':
    arguments = docopt(__doc__, version='CDMMPQTT 0.9')
    mpd_host = arguments['<mpd_host>']
    mqtt_server = arguments['<mqtt_host>']
    mqtt_client_name = arguments['<mqtt_client_name>']
    mqtt_client_password = 'ejwfoiwejfwofijf38fu98f1hfnwevlkwenvlwevjn'
    mqtt_client_id = "cdmmpqtt%d" % getnode()

    print(repr(arguments))

    root = logging.getLogger()
    # root.setLevel(logging.DEBUG)

    ch = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    root.addHandler(ch)

    mqtt_loop(mpd_host, mqtt_server, mqtt_client_id, mqtt_client_name, mqtt_client_password)
    print(arguments)


##
# Many code is stolen from here:
#       https://github.com/c-base/c-beam/blob/master/c-beamd/cbeamd/views.py
#       https://github.com/c-base/mqttwebview/
