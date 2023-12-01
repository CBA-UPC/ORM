"""
 *
 * Copyright (C) 2020 Universitat Politècnica de Catalunya.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at:
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *
"""

# -*- coding: utf-8 -*-

import argparse
import os
from datetime import datetime
import requests
import json

import config
from db_manager import Db, Connector
from utils import hash_string


def get_latest_list(size=1000000):
    # Uses Tranco API to get the latest list-ID and downloads the list with the defined size.
    # Formats the data and returns it as a python list.
    
    latest_list = requests.get("https://tranco-list.eu/api/lists/date/latest").text
    list_id = json.loads(latest_list)["list_id"]
    indexed_list = requests.get(f"https://tranco-list.eu/download/{list_id}/{size}").text
    web_list = []
    for webpage in indexed_list.split('\n'):
        if webpage != '':
            aux = webpage.split(',')[1].replace('\r','')
            web_list.append(aux)

    return web_list


def init_plugins():
    """ Initializes the default plugins"""

    # Modified uBlock Origin used as vanilla browser
    plugin = Connector(database, "plugin")
    plugin.load(hash_string('Custom uBlock Origin (Firefox)'))
    plugin.values["name"] = "Custom uBlock Origin (Firefox)"
    plugin.values["path"] = "../assets/plugin/custom_ublock_origin/custom_ublock_1.32.5.xpi"
    plugin.values["identifier"] = "custom_ublock@orm.cc"
    plugin.values["custom"] = 1
    plugin.values["url"] = "moz-extension://UUID/dashboard.html#3p-filters.html"
    plugin.values["xpath_to_click"] = "//button[@id='buttonUpdate']"
    plugin.values["enabled"] = 1
    plugin.values["background"] = "moz-extension://UUID/background.html"
    plugin.save()


def init_types():
    """ Initializes the default types """

    values = [
        ["text/html", "text/javascript", "application/javascript", 
         "application/ecmascript", "application/x-javascript", "application/x-ecmascript", 
         "text/ecmascript", "text/javascript1.0", "text/javascript1.1", 
         "text/javascript1.2", "text/javascript1.3", "text/javascript1.4", 
         "text/javascript1.5", "text/jscript", "text/livescript", 
         "text/x-javascript", "text/x-ecmascript", "Manifest",
         "text/plain", "text/css", "image/apng", "image/avif", "image/gif", "image/jpeg",
         "image/png", "image/svg+xml", "image/webp", "audio/3gpp", "audio/3gpp2", "audio/3gp2",
         "audio/aac", "audio/mpeg", "video/mpeg", "audio/flac", "audo/x-flac", "audio/mp4",
         "video/mp4", "audio/ogg", "video/ogg", "video/quicktime", "audio/wave", "audio/wav",
         "audio/x-wav", "audio/x-pn-wav", "audio/webm", "video/webm", "unknown"],
        [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
        [0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
        ["frame", "script", "script", "script", "script", "script", 
         "script", "script", "script", "script", "script", "script", 
         "script", "script", "script", "script", "script", "manifest", 
         "text", "stylesheet", "image", "image", "image", "image",
         "image", "image", "image", "media", "media", "media", 
         "media", "media", "media", "media", "media", "media", 
         "media", "media", "media", "media", "media", "media", 
         "media", "media", "media", "media", "unknown"]
    ]

    for i in range(len(values[0])):
        mime_type = Connector(database, "mime_type")
        mime_type.load(hash_string(values[0][i]))
        mime_type.values["name"] = values[0][i]
        mime_type.values["download"] = values[1][i]
        mime_type.values["beautify"] = values[2][i]
        mime_type.values["content_type"] = values[3][i]
        mime_type.save()


def init_tracking():
    """ Initializes the default types """

    values = [
        ["Session cookies", "Long-living cookies", "Very long-living cookies", "JavaScript cookies",
         "Third-party cookies", "Tracking cookies", "Font fingerprinting", "Canvas fingerprinting (small)",
         "Canvas fingerprinting (big)", "Mouse fingerprinting", "WebGL fingerprinting"],
        [1,2,3,3,4,5,4,5,6,6,6]
    ]

    for i in range(len(values[0])):
        tracking = Connector(database, "tracking")
        tracking.load(hash_string(values[0][i]))
        tracking.values["name"] = values[0][i]
        tracking.values["intrusion_level"] = values[1][i]
        tracking.save()


def init_fonts():
    """ Initializes de font table """
    with open(config.FONT_FILE_PATH, "r") as f:
        fonts = f.read()
    fonts = fonts.split(";")
    for f in fonts:
        font = Connector(database, "font")
        font.load(hash_string(f))
        font.values["name"] = f
        font.save()


def init_collectors():
    collectors = [["utiq", ["utiq.com", "utiq-aws.net"]],
                  ["ClickTale", ["clicktale.com", "clicktale.net"]], 
                  ["eTracker", ["etracker.com"]], 
                  ["hostpoint", ["clickmap.ch", "hostpoint.ch"]],
                  ["Crazyegg", ["crazyegg.com"]], 
                  ["Hotjar", ["hotjar.com"]], 
                  ["mouseflow", ["mouseflow.com"]], 
                  ["didomi", ["didomi.io", "privacy-center.org"]]]
    for c in collectors:
        collector = Connector(database, "collector")
        collector.load(hash_string(c[0]))
        collector.values["name"] = c[0]
        collector.values["url1"] = c[1][0]
        if len(c[1]) > 1:
            collector.values["url2"] = c[1][1]
        collector.save()


def init_mouse_tracking_domains():
    tracking_domains = ["clicktale.com", "clicktale.net", "etracker.com", "clickmap.ch",
                        "script.crazyegg.com", "tracking.crazyegg.com", "hotjar.com", "mouseflow.com"]
    for tracking_domain in tracking_domains:
        domain = Connector(database, "mouse_tracking_domains")
        domain.load(hash_string(tracking_domain))
        domain.values["name"] = tracking_domain
        domain.save()


parser = argparse.ArgumentParser(description='Initializes the ORM database')
parser.add_argument('-start', dest='start', type=int, default=1, help='Start index (Default 1)')
parser.add_argument('-end', dest='end', type=int, default=1000000, help='End index (Default: 1000000)', nargs='?')
parser.add_argument('-f', dest='filename', type=str, default='',
                    help='File containing one domain per line or a Tranco List csv. Can be a zip or gz file')


if __name__ == '__main__':
    args = parser.parse_args()
    start = args.start
    end = args.end

    # Initialize the database
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print("Reading domains")
    if args.filename:
        tranco_sites = config.load_csv(args.filename, 1)[slice(start - 1, end - 1, None)]
        modified = int(os.path.getmtime(args.filename))
        timestamp = datetime.utcfromtimestamp(modified).strftime('%Y-%m-%d %H:%M:%S')
    else:
        tranco_sites = get_latest_list(end)

    sites = {}
    for i, domain in enumerate(tranco_sites[start-1:end], start - 1):
        domain = domain.replace("\n\r", "").replace("\r", "").replace("\n", "")
        sites[domain] = {"tranco_rank": i+1, "name": domain}
    print("Initializing database: %d domains" % len(sites))
    database = Db()
    init_plugins()
    init_types()
    init_collectors()
    init_tracking()
    init_fonts()
    init_mouse_tracking_domains()
    database.initialize(sites, timestamp)
    database.close()
