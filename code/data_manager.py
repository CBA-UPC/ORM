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

# Basic modules
import os
import json
import logging
import logging.config
import zlib
import time

# 3rd party modules
import requests

# Own modules
from db_manager import Db, Connector
from utils import download_file, hash_file, lsh_file, hash_string, utc_now
from utils import extract_location, extract_components, extract_domain, clean_subdomain

logging.config.fileConfig('../logging.conf')

logger = logging.getLogger("DATA_MANAGER")


def insert_url(db, request, insert_ts, update_ts):
    """ Inserts the URL data into the database and returns the URL Connector. """

    # If the url is not present, the data is embedded into the url, or the resource was blocked, skip it
    if "url" not in request.keys() or request["url"][:5] == "data:" or request["url"][:6] == "chrome":
        return None
    url = Connector(db, "url")
    resource_type = Connector(db, "type")
    if not resource_type.load(hash_string(request["type"])):
        if not resource_type.save():
            resource_type.load(hash_string(request["type"]))
    components = extract_components(request["url"])
    root_url = components['netloc'] + components['path']
    if not url.load(hash_string(root_url)):
        for key in request.keys():
            if key == 'requests':
                continue
            url.values[key] = request[key]
        url.values["type"] = resource_type.values["id"]
        url.values["headers"] = str(request["headers"])
        url.values["scheme"] = components["scheme"]
        url.values["netloc"] = components["netloc"]
        url.values["path"] = components["path"]
        url.values["hostname"] = components["hostname"]
        url.values["port"] = components["port"]
        url.values["params"] = components["params"]
        url.values["query"] = components["query"]
        url.values["fragment"] = components["fragment"]
        url.values["username"] = components["username"]
        url.values["password"] = components["password"]
        url.values["insert_date"] = insert_ts
        url.values["update_timestamp"] = update_ts
        third_party = Connector(db, "domain")
        main_domain = clean_subdomain(components["netloc"].lower())
        if not third_party.load(hash_string(main_domain)):
            third_party.values["name"] = main_domain
            third_party.values["insert_date"] = insert_ts
            third_party.values["update_timestamp"] = update_ts
            if not third_party.save():
                third_party.load(hash_string(main_domain))
        url.values["domain"] = third_party.values["id"]
        if not url.save():
            url.load(hash_string(root_url))
    return url


def manage_request(db, process, domain, request, plugin, temp_folder):
    """ Inserts the URL data if non-existent and downloads/beautifies if needed """

    t = utc_now()
    # Insert new URL info
    url = insert_url(db, request, t, t)
    if not url:
        return

    # Creates the relation between domain <-> url <-> plugin
    components = extract_components(request["url"])
    root_url = components['netloc'] + components['path']
    url_type = Connector(db, "type")
    url_type.load(url.values["type"])

    resource_id = None

    # Download resource in temp file if needed
    if url_type.values["download"]:
        os.makedirs(os.path.join(os.path.abspath("."), temp_folder), exist_ok=True)
        filename = os.path.join(temp_folder, domain.values["name"] + '.tmp')
        if download_url(process, url.values["url"], filename):
            hash_code = hash_file(filename)
            size = os.stat(filename).st_size

            # Compress the code
            with open(filename, 'rb') as f:
                code = f.read()
            compressed_code = zlib.compress(code)

            # Insert resource
            resource = Connector(db, "resource")
            if not resource.load(hash_code):
                resource.values["file"] = compressed_code
                resource.values["size"] = size
                resource.values["fuzzy_hash"] = lsh_file(filename)
                resource.values["insert_date"] = t
                resource.values["update_timestamp"] = t
                if not resource.save():
                    max = 30
                    # Wait until the other thread saves the file inside the database (or 30s max)
                    while not resource.load(hash_code) and max > 0:
                        max -= 1
                        time.sleep(1)
            resource_id = resource.values["id"]
            db.call("ComputeResourceType", values=[resource_id])
            db.call("ComputeResourcePopularityLevel", values=[resource_id])

            # Remove temp file
            os.remove(filename)

        if not resource_id:
            logger.error("(proc. %s) Error #4: Resource not correctly saved" % process)

    # Compute the url length (without the domain and path)
    query_length = 0
    if url.values["params"] is not None:
        query_length += len(url.values["params"])
    if url.values["query"] is not None:
        query_length += len(url.values["query"])
    if url.values["fragment"] is not None:
        query_length += len(url.values["fragment"])
    if url.values["username"] is not None:
        query_length += len(url.values["username"])
    if url.values["password"] is not None:
        query_length += len(url.values["password"])

    domain.add_double(url, plugin, {"resource_id": resource_id, "query_length": query_length,
                                    "insert_date": t, "update_timestamp": t})

    if not resource_id:
        query = "INSERT INTO log (domain_id, plugin_id, url) VALUES (%s, %s, %s)"
        db.custom(query=query, values=[domain.values["id"], plugin.values["id"], request["url"]])
    else:
        query = "INSERT INTO log (domain_id, plugin_id, url, resource_id) VALUES (%s, %s, %s, %s)"
        db.custom(query=query, values=[domain.values["id"], plugin.values["id"], request["url"], resource_id])

    # Add subdomain or third party
#    subdomain = components["netloc"].lower()
#    main_domain = clean_subdomain(subdomain)
#    if main_domain == domain.values["name"]:
#        subdomain = subdomain.partition(".")[0]
#        sub = Connector(db, "subdomain")
#        if not sub.load(hash_string(subdomain)):
#            sub.values["name"] = subdomain
#            if not sub.save():
#                sub.load(hash_string(subdomain))
#        t = utc_now()
#        domain.add(sub, {"insert_date": t, "update_timestamp": t})
#    else:
#        third_party = Connector(db, "third_party")
#        if not third_party.load(hash_string(main_domain)):
#            third_party.values["name"] = main_domain
#            if not third_party.save():
#                third_party.load(hash_string(main_domain))
#        t = utc_now()
#        domain.add(third_party, {"insert_date": t, "update_timestamp": t})


def download_url(process, url, filename):
    """ Downloads the given url into the given filename. """

    with open(filename, 'wb') as f:
        try:
            f, headers = download_file(url=url, destination=f)
        except requests.exceptions.SSLError:
            try:
                requests.packages.urllib3.disable_warnings()
                f, headers = download_file(url=url, destination=f, verify=False)
            except Exception as e:
                logger.error("(proc. %s) Error #1: %s" % (process, str(e)))
                return False
        except UnicodeError as e:
            logger.error("(proc. %s) Error #2: Couldn't download url %s with error %s" % (process, url, str(e)))
            return False
        except Exception as e:
            logger.error("(proc. %s) Error #3: %s" % (process, str(e)))
            return False
    logger.debug("(proc. %s) Found external resource %s" % (process, url))
    return True


def get_network(log_entries):
    """ Reads the performance log entries and computes a network traffic dictionary based on the actual requests. """

    network_traffic = {}
    for log_entry in log_entries:
        message = json.loads(log_entry["message"])
        method = message["message"]["method"]
        params = message["message"]["params"]
        if method not in ["Network.requestWillBeSent", "Network.responseReceived", "Network.loadingFinished"]:
            continue
        if method != "Network.loadingFinished":
            request_id = params["requestId"]
            loader_id = params["loaderId"]
            if loader_id not in network_traffic:
                network_traffic[loader_id] = {"requests": {}, "encoded_data_length": 0}
            if request_id == loader_id:
                if "redirectResponse" in params:
                    network_traffic[loader_id]["encoded_data_length"] += params["redirectResponse"]["encodedDataLength"]
                if method == "Network.responseReceived":
                    network_traffic[loader_id]["type"] = params["type"]
                    network_traffic[loader_id]["url"] = params["response"]["url"]
                    network_traffic[loader_id]["remote_IP_address"] = None
                    if "remoteIPAddress" in params["response"].keys():
                        network_traffic[loader_id]["remote_IP_address"] = params["response"]["remoteIPAddress"]
                    network_traffic[loader_id]["encoded_data_length"] += params["response"]["encodedDataLength"]
                    network_traffic[loader_id]["headers"] = params["response"]["headers"]
                    network_traffic[loader_id]["status"] = params["response"]["status"]
                    network_traffic[loader_id]["security_state"] = params["response"]["securityState"]
                    network_traffic[loader_id]["mime_type"] = params["response"]["mimeType"]
                    if "via" in params["response"]["headers"]:
                        network_traffic[loader_id]["cached"] = True
            else:
                if request_id not in network_traffic[loader_id]["requests"]:
                    network_traffic[loader_id]["requests"][request_id] = {"encoded_data_length": 0}
                if "redirectResponse" in params:
                    network_traffic[loader_id]["requests"][request_id]["encoded_data_length"] += params["redirectResponse"]["encodedDataLength"]
                if method == "Network.responseReceived":
                    network_traffic[loader_id]["requests"][request_id]["type"] = params["type"]
                    network_traffic[loader_id]["requests"][request_id]["url"] = params["response"]["url"]
                    network_traffic[loader_id]["requests"][request_id]["remote_IP_address"] = None
                    if "remoteIPAddress" in params["response"].keys():
                        network_traffic[loader_id]["requests"][request_id]["remote_IP_address"] = params["response"]["remoteIPAddress"]
                    network_traffic[loader_id]["requests"][request_id]["encoded_data_length"] += params["response"]["encodedDataLength"]
                    network_traffic[loader_id]["requests"][request_id]["headers"] = params["response"]["headers"]
                    network_traffic[loader_id]["requests"][request_id]["status"] = params["response"]["status"]
                    network_traffic[loader_id]["requests"][request_id]["security_state"] = params["response"]["securityState"]
                    network_traffic[loader_id]["requests"][request_id]["mime_type"] = params["response"]["mimeType"]
                    if "via" in params["response"]["headers"]:
                        network_traffic[loader_id]["requests"][request_id]["cached"] = 1
        else:
            request_id = params["requestId"]
            encoded_data_length = params["encodedDataLength"]
            for loader_id in network_traffic:
                if request_id == loader_id:
                    network_traffic[loader_id]["encoded_data_length"] += encoded_data_length
                elif request_id in network_traffic[loader_id]["requests"]:
                    network_traffic[loader_id]["requests"][request_id]["encoded_data_length"] += encoded_data_length
    return network_traffic

