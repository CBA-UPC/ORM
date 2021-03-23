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

import config
from db_manager import Db, Connector
from utils import hash_string


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

    mime_type = Connector(database, "mime_type")
    mime_type.load(hash_string("text/html"))
    mime_type.values["name"] = "text/html"
    mime_type.values["download"] = 1
    mime_type.values["beautify"] = 0
    mime_type.values["content_type"] = "frame"
    mime_type.save()

    mime_type.load(hash_string("text/javascript"))
    mime_type.values["name"] = "text/javascript"
    mime_type.values["download"] = 1
    mime_type.values["beautify"] = 1
    mime_type.values["content_type"] = "script"
    mime_type.save()

    mime_type.load(hash_string("application/javascript"))
    mime_type.values["name"] = "application/javascript"
    mime_type.values["download"] = 1
    mime_type.values["beautify"] = 1
    mime_type.values["content_type"] = "script"
    mime_type.save()

    mime_type.load(hash_string("application/ecmascript"))
    mime_type.values["name"] = "application/ecmascript"
    mime_type.values["download"] = 1
    mime_type.values["beautify"] = 1
    mime_type.values["content_type"] = "script"
    mime_type.save()

    mime_type.load(hash_string("application/x-javascript"))
    mime_type.values["name"] = "application/x-javascript"
    mime_type.values["download"] = 1
    mime_type.values["beautify"] = 1
    mime_type.values["content_type"] = "script"
    mime_type.save()

    mime_type.load(hash_string("application/x-ecmascript"))
    mime_type.values["name"] = "application/x-ecmascript"
    mime_type.values["download"] = 1
    mime_type.values["beautify"] = 1
    mime_type.values["content_type"] = "script"
    mime_type.save()

    mime_type.load(hash_string("text/ecmascript"))
    mime_type.values["name"] = "text/ecmascript"
    mime_type.values["download"] = 1
    mime_type.values["beautify"] = 1
    mime_type.values["content_type"] = "script"
    mime_type.save()

    mime_type.load(hash_string("text/javascript1.0"))
    mime_type.values["name"] = "text/javascript1.0"
    mime_type.values["download"] = 1
    mime_type.values["beautify"] = 1
    mime_type.values["content_type"] = "script"
    mime_type.save()

    mime_type.load(hash_string("text/javascript1.1"))
    mime_type.values["name"] = "text/javascript1.1"
    mime_type.values["download"] = 1
    mime_type.values["beautify"] = 1
    mime_type.values["content_type"] = "script"
    mime_type.save()

    mime_type.load(hash_string("text/javascript1.2"))
    mime_type.values["name"] = "text/javascript1.2"
    mime_type.values["download"] = 1
    mime_type.values["beautify"] = 1
    mime_type.values["content_type"] = "script"
    mime_type.save()

    mime_type.load(hash_string("text/javascript1.3"))
    mime_type.values["name"] = "text/javascript1.3"
    mime_type.values["download"] = 1
    mime_type.values["beautify"] = 1
    mime_type.values["content_type"] = "script"
    mime_type.save()

    mime_type.load(hash_string("text/javascript1.4"))
    mime_type.values["name"] = "text/javascript1.4"
    mime_type.values["download"] = 1
    mime_type.values["beautify"] = 1
    mime_type.values["content_type"] = "script"
    mime_type.save()

    mime_type.load(hash_string("text/javascript1.5"))
    mime_type.values["name"] = "text/javascript1.5"
    mime_type.values["download"] = 1
    mime_type.values["beautify"] = 1
    mime_type.values["content_type"] = "script"
    mime_type.save()

    mime_type.load(hash_string("text/jscript"))
    mime_type.values["name"] = "text/jscript"
    mime_type.values["download"] = 1
    mime_type.values["beautify"] = 1
    mime_type.values["content_type"] = "script"
    mime_type.save()

    mime_type.load(hash_string("text/livescript"))
    mime_type.values["name"] = "text/livescript"
    mime_type.values["download"] = 1
    mime_type.values["beautify"] = 1
    mime_type.values["content_type"] = "script"
    mime_type.save()

    mime_type.load(hash_string("text/x-javascript"))
    mime_type.values["name"] = "text/x-javascript"
    mime_type.values["download"] = 1
    mime_type.values["beautify"] = 1
    mime_type.values["content_type"] = "script"
    mime_type.save()

    mime_type.load(hash_string("text/x-ecmascript"))
    mime_type.values["name"] = "text/x-ecmascript"
    mime_type.values["download"] = 1
    mime_type.values["beautify"] = 1
    mime_type.values["content_type"] = "script"
    mime_type.save()

    mime_type.load(hash_string("Manifest"))
    mime_type.values["name"] = "Manifest"
    mime_type.values["download"] = 0
    mime_type.values["beautify"] = 0
    mime_type.values["content_type"] = "other"
    mime_type.save()

    mime_type.load(hash_string("text/plain"))
    mime_type.values["name"] = "text/plain"
    mime_type.values["download"] = 0
    mime_type.values["beautify"] = 0
    mime_type.values["content_type"] = "text"
    mime_type.save()

    mime_type.load(hash_string("text/css"))
    mime_type.values["name"] = "text/css"
    mime_type.values["download"] = 0
    mime_type.values["beautify"] = 0
    mime_type.values["content_type"] = "stylesheet"
    mime_type.save()

    mime_type.load(hash_string("image/apng"))
    mime_type.values["name"] = "image/apng"
    mime_type.values["download"] = 0
    mime_type.values["beautify"] = 0
    mime_type.values["content_type"] = "image"
    mime_type.save()

    mime_type.load(hash_string("image/avif"))
    mime_type.values["name"] = "image/avif"
    mime_type.values["download"] = 0
    mime_type.values["beautify"] = 0
    mime_type.values["content_type"] = "image"
    mime_type.save()

    mime_type.load(hash_string("image/gif"))
    mime_type.values["name"] = "image/gif"
    mime_type.values["download"] = 0
    mime_type.values["beautify"] = 0
    mime_type.values["content_type"] = "image"
    mime_type.save()

    mime_type.load(hash_string("image/jpeg"))
    mime_type.values["name"] = "image/jpeg"
    mime_type.values["download"] = 0
    mime_type.values["beautify"] = 0
    mime_type.values["content_type"] = "image"
    mime_type.save()

    mime_type.load(hash_string("image/png"))
    mime_type.values["name"] = "image/png"
    mime_type.values["download"] = 0
    mime_type.values["beautify"] = 0
    mime_type.values["content_type"] = "image"
    mime_type.save()

    mime_type.load(hash_string("image/svg+xml"))
    mime_type.values["name"] = "image/svg+xml"
    mime_type.values["download"] = 0
    mime_type.values["beautify"] = 0
    mime_type.values["content_type"] = "image"
    mime_type.save()

    mime_type.load(hash_string("image/webp"))
    mime_type.values["name"] = "image/webp"
    mime_type.values["download"] = 0
    mime_type.values["beautify"] = 0
    mime_type.values["content_type"] = "image"
    mime_type.save()

    mime_type.load(hash_string("audio/3gpp"))
    mime_type.values["name"] = "audio/3gpp"
    mime_type.values["download"] = 0
    mime_type.values["beautify"] = 0
    mime_type.values["content_type"] = "media"
    mime_type.save()

    mime_type.load(hash_string("audio/3gpp2"))
    mime_type.values["name"] = "audio/3gpp2"
    mime_type.values["download"] = 0
    mime_type.values["beautify"] = 0
    mime_type.values["content_type"] = "media"
    mime_type.save()

    mime_type.load(hash_string("audio/3gp2"))
    mime_type.values["name"] = "audio/3gp2"
    mime_type.values["download"] = 0
    mime_type.values["beautify"] = 0
    mime_type.values["content_type"] = "media"
    mime_type.save()

    mime_type.load(hash_string("audio/aac"))
    mime_type.values["name"] = "audio/aac"
    mime_type.values["download"] = 0
    mime_type.values["beautify"] = 0
    mime_type.values["content_type"] = "media"
    mime_type.save()

    mime_type.load(hash_string("audio/mpeg"))
    mime_type.values["name"] = "audio/mpeg"
    mime_type.values["download"] = 0
    mime_type.values["beautify"] = 0
    mime_type.values["content_type"] = "media"
    mime_type.save()

    mime_type.load(hash_string("video/mpeg"))
    mime_type.values["name"] = "video/mpeg"
    mime_type.values["download"] = 0
    mime_type.values["beautify"] = 0
    mime_type.values["content_type"] = "media"
    mime_type.save()

    mime_type.load(hash_string("audio/flac"))
    mime_type.values["name"] = "audio/flac"
    mime_type.values["download"] = 0
    mime_type.values["beautify"] = 0
    mime_type.values["content_type"] = "media"
    mime_type.save()

    mime_type.load(hash_string("audio/x-flac"))
    mime_type.values["name"] = "audio/x-flac"
    mime_type.values["download"] = 0
    mime_type.values["beautify"] = 0
    mime_type.values["content_type"] = "media"
    mime_type.save()

    mime_type.load(hash_string("audio/mp4"))
    mime_type.values["name"] = "audio/mp4"
    mime_type.values["download"] = 0
    mime_type.values["beautify"] = 0
    mime_type.values["content_type"] = "media"
    mime_type.save()

    mime_type.load(hash_string("video/mp4"))
    mime_type.values["name"] = "video/mp4"
    mime_type.values["download"] = 0
    mime_type.values["beautify"] = 0
    mime_type.values["content_type"] = "media"
    mime_type.save()

    mime_type.load(hash_string("audio/ogg"))
    mime_type.values["name"] = "audio/ogg"
    mime_type.values["download"] = 0
    mime_type.values["beautify"] = 0
    mime_type.values["content_type"] = "media"
    mime_type.save()

    mime_type.load(hash_string("video/ogg"))
    mime_type.values["name"] = "video/ogg"
    mime_type.values["download"] = 0
    mime_type.values["beautify"] = 0
    mime_type.values["content_type"] = "media"
    mime_type.save()

    mime_type.load(hash_string("video/quicktime"))
    mime_type.values["name"] = "video/quicktime"
    mime_type.values["download"] = 0
    mime_type.values["beautify"] = 0
    mime_type.values["content_type"] = "media"
    mime_type.save()

    mime_type.load(hash_string("audio/wave"))
    mime_type.values["name"] = "audio/wave"
    mime_type.values["download"] = 0
    mime_type.values["beautify"] = 0
    mime_type.values["content_type"] = "media"
    mime_type.save()

    mime_type.load(hash_string("audio/wav"))
    mime_type.values["name"] = "audio/wav"
    mime_type.values["download"] = 0
    mime_type.values["beautify"] = 0
    mime_type.values["content_type"] = "media"
    mime_type.save()

    mime_type.load(hash_string("audio/x-wav"))
    mime_type.values["name"] = "audio/x-wav"
    mime_type.values["download"] = 0
    mime_type.values["beautify"] = 0
    mime_type.values["content_type"] = "media"
    mime_type.save()

    mime_type.load(hash_string("audio/x-pn-wav"))
    mime_type.values["name"] = "audio/x-pn-wav"
    mime_type.values["download"] = 0
    mime_type.values["beautify"] = 0
    mime_type.values["content_type"] = "media"
    mime_type.save()

    mime_type.load(hash_string("audio/webm"))
    mime_type.values["name"] = "audio/webm"
    mime_type.values["download"] = 0
    mime_type.values["beautify"] = 0
    mime_type.values["content_type"] = "media"
    mime_type.save()

    mime_type.load(hash_string("video/webm"))
    mime_type.values["name"] = "video/webm"
    mime_type.values["download"] = 0
    mime_type.values["beautify"] = 0
    mime_type.values["content_type"] = "media"
    mime_type.save()

    mime_type = Connector(database, "mime_type")
    mime_type.load(hash_string("unknown"))
    mime_type.values["name"] = "unknown"
    mime_type.values["download"] = 0
    mime_type.values["beautify"] = 0
    mime_type.values["content_type"] = "unknown"
    mime_type.save()


def init_tracking():
    """ Initializes the default types """

    tracking = Connector(database, "tracking")
    tracking.load(hash_string("Cookies"))
    tracking.values["name"] = "Cookies"
    tracking.values["intrusion_level"] = 1
    tracking.save()

    tracking = Connector(database, "tracking")
    tracking.load(hash_string("Canvas fingerprinting"))
    tracking.values["name"] = "Canvas fingerprinting"
    tracking.values["intrusion_level"] = 3
    tracking.save()

    tracking = Connector(database, "Tracking")
    tracking.load(hash_string("Mouse tracking"))
    tracking.values["name"] = "mouse tracking"
    tracking.values["intrusion_level"] = 3
    tracking.save()


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

