'''
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
'''

# -*- coding: utf-8 -*-

import argparse
import os
from datetime import datetime

import config
from db_manager import Db, Connector
from utils import hash_string


def init_plugins():
    """ Initializes the default plugins"""

    # Vanilla
    plugin = Connector(database, "plugin")
    plugin.load(hash_string('Vanilla'))
    plugin.values["name"] = "Vanilla"
    plugin.values["path"] = None
    plugin.values["custom"] = 0
    plugin.values["url"] = None
    plugin.values["xpath_to_click"] = None
    plugin.values["enabled"] = 1
    plugin.save()

    # AdBlock Plus
    plugin.load(hash_string('AdBlock Plus'))
    plugin.values["name"] = "AdBlock Plus"
    plugin.values["path"] = "../assets/plugin/adblock_plus/3.10.1.crx"
    plugin.values["custom"] = 1
    plugin.values["url"] = "chrome-extension://cfhdojbkjhnklbpkdaibdccddilifddb/options.html"
    plugin.values["xpath_to_click"] = "//button[@data-action='toggle-remove-subscription']"
    plugin.values["enabled"] = 1
    plugin.save()

    # Ghostery
    plugin.load(hash_string('Ghostery'))
    plugin.values["name"] = "Ghostery"
    plugin.values["path"] = "../assets/plugin/ghostery/8.5.4.crx"
    plugin.values["custom"] = 0
    plugin.values["url"] = None
    plugin.values["xpath_to_click"] = None
    plugin.values["enabled"] = 1
    plugin.save()

    # Ublock Origin
    plugin.load(hash_string('Ublock Origin'))
    plugin.values["name"] = "Ublock Origin"
    plugin.values["path"] = "../assets/plugin/ublock_origin/1.32.4.crx"
    plugin.values["custom"] = 1
    plugin.values["url"] = "chrome-extension://iifehfkdbojjjlccddcaadcadlgkljjm/dashboard.html#3p-filters.html"
    plugin.values["xpath_to_click"] = "//button[@id='buttonUpdate']"
    plugin.values["enabled"] = 1
    plugin.save()


def init_types():
    """ Initializes the default types to download """

    ctype = Connector(database, "type")
    ctype.load(hash_string("Document"))
    ctype.values["name"] = "Document"
    ctype.values["content_list_type"] = "document"
    ctype.save()

    ctype.load(hash_string("Script"))
    ctype.values["name"] = "Script"
    ctype.values["content_list_type"] = "script"
    ctype.save()

    ctype.load(hash_string("Stylesheet"))
    ctype.values["name"] = "Stylesheet"
    ctype.values["content_list_type"] = "stylesheet"
    ctype.save()

    ctype.load(hash_string("Manifest"))
    ctype.values["name"] = "Manifest"
    ctype.values["content_list_type"] = "other"
    ctype.save()

    ctype.load(hash_string("XHR"))
    ctype.values["name"] = "XHR"
    ctype.values["content_list_type"] = "xmlhttprequest"
    ctype.save()

    ctype.load(hash_string("Fetch"))
    ctype.values["name"] = "Fetch"
    ctype.values["content_list_type"] = "xmlhttprequest"
    ctype.save()

    ctype.load(hash_string("Image"))
    ctype.values["name"] = "Image"
    ctype.values["content_list_type"] = "image"
    ctype.save()

    ctype.load(hash_string("Media"))
    ctype.values["name"] = "Media"
    ctype.values["content_list_type"] = "media"
    ctype.save()

    ctype.load(hash_string("Font"))
    ctype.values["name"] = "Font"
    ctype.values["content_list_type"] = "font"
    ctype.save()

    ctype.load(hash_string("WebRTC"))
    ctype.values["name"] = "WebRTC"
    ctype.values["content_list_type"] = "webrtc"
    ctype.save()

    ctype.load(hash_string("WebSocket"))
    ctype.values["name"] = "WebSocket"
    ctype.values["content_list_type"] = "websocket"
    ctype.save()

    ctype.load(hash_string("TextTrack"))
    ctype.values["name"] = "TextTrack"
    ctype.values["content_list_type"] = "object"
    ctype.save()

    ctype.load(hash_string("EventSource"))
    ctype.values["name"] = "EventSource"
    ctype.values["content_list_type"] = "other"
    ctype.save()

    ctype.load(hash_string("Other"))
    ctype.values["name"] = "Other"
    ctype.values["content_list_type"] = "other"
    ctype.save()


parser = argparse.ArgumentParser(description='Initializes the ORM database')
parser.add_argument('start', type=int, default=0, help='Start index (0 indexed)')
parser.add_argument('end', type=int, help='End index (not included)', nargs='?')
parser.add_argument('-f', dest='filename', type=str, default='../assets/alexa/top-1m.csv.zip',
                    help='File containing one domain per line or an alexa csv. Can be a zip or gz file')


if __name__ == '__main__':
    args = parser.parse_args()
    start = args.start
    end = args.end
    sites_length = end - start

    # Initialize the database
    modified = int(os.path.getmtime(args.filename))
    timestamp = datetime.utcfromtimestamp(modified).strftime('%Y-%m-%d %H:%M:%S')
    sites = config.load_csv(args.filename, 1)[slice(start, end, None)]
    print("Initializing database")
    database = Db()
    init_plugins()
    init_types()
    database.initialize(sites, start, timestamp)
    database.close()

