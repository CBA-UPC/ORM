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
from utils import extract_components, extract_domain, clean_subdomain

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
        if not url.save():
            url.load(hash_string(root_url))
    return url


def manage_request(db, domain, request, plugin):
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

    domain.add_double(url, plugin, {"query_length": query_length, "insert_date": t, "update_timestamp": t})

    query = "INSERT INTO log (domain_id, plugin_id, url) VALUES (%s, %s, %s)"
    db.custom(query=query, values=[domain.values["id"], plugin.values["id"], request["url"]])


def get_network(log_entries):
    """ Reads the performance log entries and computes a network traffic dictionary based on the actual requests. """

    network_traffic = {}
    for log_entry in log_entries:
        method = log_entry["method"]
        params = log_entry["params"]
        if method not in ["Network.requestWillBeSent", "Network.responseReceived", "Network.loadingFinished"]:
            continue
        if method != "Network.loadingFinished":
            request_id = params["requestId"]
            loader_id = params["loaderId"]
            if loader_id not in network_traffic:
                network_traffic[loader_id] = {"requests": {}, "encoded_data_length": 0}
            if request_id == loader_id:
                #if "redirectResponse" in params:
                #    network_traffic[loader_id]["encoded_data_length"] += params["redirectResponse"]["encodedDataLength"]
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
                # if "redirectResponse" in params:
                #    network_traffic[loader_id]["requests"][request_id]["encoded_data_length"] += params["redirectResponse"]["encodedDataLength"]
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


def get_performance(db, domain, plugin, log, trace):
    """ Reads the lighthouse log entries and inserts inside DB a QoE entry. """

    t = utc_now()
    qoe = Connector(db, "QoE")
    qoe.values["domain_id"] = domain.values["id"]
    qoe.values["plugin_id"] = plugin.values["id"]
    try:
        qoe.values["performance"] = float(log["categories"]["performance"]["score"])
        qoe.values["speed_index"] = float(log["audits"]["speed-index"]["numericValue"])
        qoe.values["speed_index_score"] = float(log["audits"]["speed-index"]["score"])
        qoe.values["first_contentful_paint"] = float(log["audits"]["first-contentful-paint"]["numericValue"])
        qoe.values["first_contentful_paint_score"] = float(log["audits"]["first-contentful-paint"]["score"])
        qoe.values["largest_contentful_paint"] = float(log["audits"]["largest-contentful-paint"]["numericValue"])
        qoe.values["largest_contentful_paint_score"] = float(log["audits"]["largest-contentful-paint"]["score"])
        qoe.values["first_meaningful_paint"] = float(log["audits"]["first-meaningful-paint"]["numericValue"])
        qoe.values["first_meaningful_paint_score"] = float(log["audits"]["first-meaningful-paint"]["score"])
        qoe.values["estimated_input_latency"] = float(log["audits"]["estimated-input-latency"]["numericValue"])
        qoe.values["estimated_input_latency_score"] = float(log["audits"]["estimated-input-latency"]["score"])
        qoe.values["total_blocking_time"] = float(log["audits"]["total-blocking-time"]["numericValue"])
        qoe.values["total_blocking_time_score"] = float(log["audits"]["total-blocking-time"]["score"])
        qoe.values["max_potential_fid_score"] = float(log["audits"]["max-potential-fid"]["score"])
        qoe.values["cumulative_layout_shift_score"] = float(log["audits"]["cumulative-layout-shift"]["score"])
        qoe.values["first_cpu_idle"] = float(log["audits"]["first-cpu-idle"]["numericValue"])
        qoe.values["server_response_time"] = float(log["audits"]["server-response-time"]["numericValue"])
        qoe.values["interactive"] = float(log["audits"]["interactive"]["numericValue"])
        qoe.values["interactive_score"] = float(log["audits"]["interactive"]["score"])
        qoe.values["dom_size"] = int(log["audits"]["dom-size"]["numericValue"])
        qoe.values["redirects"] = float(log["audits"]["redirects"]["numericValue"])
        qoe.values["rtt"] = float(log["audits"]["diagnostics"]["details"]["items"][0]["rtt"])
        qoe.values["max_rtt"] = float(log["audits"]["diagnostics"]["details"]["items"][0]["maxRtt"])
        qoe.values["throughput"] = float(log["audits"]["diagnostics"]["details"]["items"][0]["throughput"])
        qoe.values["max_server_latency"] = float(log["audits"]["diagnostics"]["details"]["items"][0]["maxServerLatency"])
        qoe.values["total_byte_weight"] = float(log["audits"]["diagnostics"]["details"]["items"][0]["totalByteWeight"])
        qoe.values["total_task_time"] = float(log["audits"]["diagnostics"]["details"]["items"][0]["totalTaskTime"])
        qoe.values["num_scripts"] = int(log["audits"]["diagnostics"]["details"]["items"][0]["numScripts"])
        qoe.values["num_stylesheets"] = int(log["audits"]["diagnostics"]["details"]["items"][0]["numStylesheets"])
        qoe.values["num_fonts"] = int(log["audits"]["diagnostics"]["details"]["items"][0]["numFonts"])
        qoe.values["num_tasks"] = int(log["audits"]["diagnostics"]["details"]["items"][0]["numTasks"])
        qoe.values["num_tasks_over_10ms"] = int(log["audits"]["diagnostics"]["details"]["items"][0]["numTasksOver10ms"])
        qoe.values["num_tasks_over_25ms"] = int(log["audits"]["diagnostics"]["details"]["items"][0]["numTasksOver25ms"])
        qoe.values["num_tasks_over_50ms"] = int(log["audits"]["diagnostics"]["details"]["items"][0]["numTasksOver50ms"])
        qoe.values["num_tasks_over_100ms"] = int(log["audits"]["diagnostics"]["details"]["items"][0]["numTasksOver100ms"])
        qoe.values["num_tasks_over_500ms"] = int(log["audits"]["diagnostics"]["details"]["items"][0]["numTasksOver500ms"])
        qoe.values["long_tasks"] = len(log["audits"]["long-tasks"]["details"]["items"])
        for item in log["audits"]["resource-summary"]["details"]["items"]:
            if item["label"] == "Total":
                qoe.values["resource_summary_total"] = int(item["requestCount"])
            elif item["label"] == "Media":
                qoe.values["resource_summary_media"] = int(item["requestCount"])
            elif item["label"] == "Script":
                qoe.values["resource_summary_scripts"] = int(item["requestCount"])
            elif item["label"] == "Image":
                qoe.values["resource_summary_image"] = int(item["requestCount"])
            elif item["label"] == "Document":
                qoe.values["resource_summary_document"] = int(item["requestCount"])
            elif item["label"] == "Font":
                qoe.values["resource_summary_font"] = int(item["requestCount"])
            elif item["label"] == "Other":
                qoe.values["resource_summary_other"] = int(item["requestCount"])
            elif item["label"] == "Stylesheet":
                qoe.values["resource_summary_stylesheet"] = int(item["requestCount"])
            elif item["label"] == "Third-party":
                qoe.values["resource_summary_third_party"] = int(item["requestCount"])
        qoe.values["errors_in_console"] = len(log["audits"]["errors-in-console"]["details"]["items"])
        qoe.values["inspector_issues"] = len(log["audits"]["inspector-issues"]["details"]["items"])
        # Compress the code
#        compressed_perf_log = zlib.compress(str(trace).encode("utf-8"))
#        compressed_lh_log = zlib.compress(str(log).encode("utf-8"))
#        qoe.values["performance_log"] = compressed_perf_log
#        qoe.values["lighthouse_log"] = compressed_lh_log
        qoe.values["insert_date"] = t
        qoe.values["update_timestamp"] = t
    except Exception as e:
        logger.error("(proc. %d) Lighthouse error on website %s" % (process, domain.values["name"]))
        return
    return qoe.save()

