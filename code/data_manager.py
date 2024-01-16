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

# Basic modules
import os
import json
import logging
import logging.config
import zlib
import time
import re

# 3rd party modules
import requests
from bs4 import BeautifulSoup
from asn1crypto import pem

# Own modules
from db_manager import Db, Connector
from tracking_manager import check_tracking
from utils import download_file, hash_file, lsh_file, hash_string, utc_now, extract_domain
from utils import certificate_to_json, extract_location, clean_subdomain

logging.config.fileConfig('logging.conf')

logger = logging.getLogger("DATA_MANAGER")


def manage_requests(db, process, domain, request_list, temp_folder, geo_db):
    """ Inserts the URL data if non-existent and downloads resources if needed """

    t = utc_now()

    # Clean malformed URL info groups
    # TODO: Check the reason for the malformed ones
    keys_to_delete = []
    for key in request_list.keys():
        elem = json.loads(request_list[key])
        if not isinstance(elem, dict) or "requestId" not in elem.keys():
            keys_to_delete.append(key)
            logger.info("[Worker %s] : URL details not present - %s" % (process, key))
    for key in keys_to_delete:
        request_list.pop(key)

    url_dict = []
    # Insert certificates info
    for url_string in request_list.keys():
        url_info = json.loads(request_list[url_string])
        if "security_info" not in url_info.keys():
            url_dict.append(url_info)
            continue
        security_info = url_info["security_info"]
        if "certificates" in security_info.keys() and len(security_info["certificates"]) > 0:
            der_certificate = ''.join(format(x, '02x') for x in security_info["certificates"][0]["rawDER"])
            certificate_hash = hash_string(der_certificate)
            certificate = Connector(db, "certificate")
            if not certificate.load(certificate_hash):
                pem_bytes = pem.armor('CERTIFICATE', bytes.fromhex(der_certificate))
                certificate.values["file"] = zlib.compress(pem_bytes)
                os.makedirs(temp_folder, exist_ok=True)
                with open(os.path.join(temp_folder, domain.values["name"] + ".pem"), "bw") as f:
                    f.write(pem_bytes)
                certificate_json = certificate_to_json(os.path.join(temp_folder, domain.values["name"] + ".pem"))
                try:
                    os.remove(os.path.join(temp_folder, domain.values["name"] + ".pem"))
                except Exception:
                    # In case that other process saved the same certificate at the same time and deleted the file
                    pass
                certificate.values["json"] = json.dumps(certificate_json)
                if not certificate.save():
                    certificate.load(certificate_hash)
            security_info.pop("certificates")
            url_info["certificate"] = certificate.values["id"]
        url_info["security_info"] = security_info
        url_dict.append(url_info)

    collectors = Connector(db, "collector")
    collectors = collectors.get_all()

    # Insert URL info
    # We sort them by request id and timestamp to link parent urls with child ones
    for elem in sorted(url_dict, key=lambda i: (int(i["requestId"]), int(i["timeStamp"]))):
        url = Connector(db, "url")
        # If not previously seen URL insert it
        if not url.load(hash_string(elem["url"])):
            url.values["url"] = elem["url"]
            url.values["method"] = elem["method"]
            url.values["type"] = elem["type"]
            url.values["host"] = clean_subdomain(elem["url"])
            if elem["blocked"]:
                url.values["blocked"] = 1
            # If not in browser cache try to get address properties
            if "from_cache" in elem.keys():
                url.values["from_cache"] = elem["from_cache"]
                if "request_headers" in elem.keys():
                    url.values["request_headers"] = json.dumps(elem["request_headers"])
            # Save headers in JSON format and try to find the mime type of the file
            content_type = Connector(db, "mime_type")
            if "response_headers" in elem.keys():
                url.values["response_headers"] = json.dumps(elem["response_headers"])
                if "content-type" in elem["response_headers"]:
                    if not content_type.load(hash_string(elem["response_headers"]["content-type"].split(";")[0])):
                        content_type.values["name"] = elem["response_headers"]["content-type"].split(";")[0]
                        if re.search("text", content_type.values["name"]) or re.search("script", content_type.values["name"]):
                            content_type.values["download"] = 1
                        if not content_type.save():
                            content_type.load(hash_string(elem["response_headers"]["content-type"].split(";")[0]))
                else:
                    content_type.load(hash_string("unknown"))
            else:
                content_type.load(hash_string("unknown"))
            url.values["mime_type_id"] = content_type.values["id"]
            # Link the certificate
            if "security_info" in elem.keys():
                url.values["security_info"] = json.dumps(elem["security_info"])
            if "certificate" in elem.keys():
                url.values["certificate_id"] = elem["certificate"]
            # Create the resource element if needed and link it
            if "hash" in elem.keys():
                resource = Connector(db, "resource")
                if not resource.load(elem["hash"]):
                    if elem["blocked"]:
                        resource.values["is_tracking"] = 1
                    resource.values["insert_date"] = t
                    resource.values["update_timestamp"] = t
                    if not resource.save():
                        resource.load(elem["hash"])
                url.values["resource_id"] = resource.values["id"]
            url.values["insert_date"] = t
            url.values["update_timestamp"] = t
            if not url.save():
                # Wait until the other thread saves the URL inside the database (or 30s max)
                seconds = 30
                while not url.load(hash_string(elem["url"])) and seconds > 0:
                    seconds -= 1
                    time.sleep(1)
        else:
            # I URL has already been found update the timestamp
            url.values["update_timestamp"] = t
            url.save()
        if "server_ip" in elem.keys():
            host_domain = clean_subdomain(elem["url"])
            host = Connector(db, "host")
            if not host.load(hash_string(host_domain)):
                host.values["name"] = host_domain
                host.values["insert_date"] = t
                host.values["update_timestamp"] = t
                if not host.save():
                    host.load(hash_string(host_domain))
            address = Connector(db, "address")
            if not address.load(hash_string(elem["server_ip"])):
                address.values["address"] = elem["server_ip"]
                address.values["is_EU"] = 0
                address.values["insert_date"] = t
                address.values["update_timestamp"] = t
                location = extract_location(elem["server_ip"], geo_db)
                if location["is_EU"]:
                    address.values["is_EU"] = 1
                address.values["country_code"] = location["country_code"]
                if not address.save():
                    address.load(hash_string(elem["server_ip"]))
            host.add(address)
            url.add(address)

        # Depending on the resource type download it if needed
        content_type = Connector(db, "mime_type")
        content_type.load(url.values["mime_type_id"])
        if content_type.values["download"]:
            resource = Connector(db, "resource")
            if url.values["resource_id"] or "hash" in elem.keys():
                if url.values["resource_id"]:
                    resource.load(url.values["resource_id"])
                elif "hash" in elem.keys():
                    if not resource.load(elem["hash"]):
                        if elem["blocked"]:
                            resource.values["is_tracking"] = 1
                        resource.values["insert_date"] = t
                        resource.values["update_timestamp"] = t
                        if not resource.save():
                            resource.load(elem["hash"])
                        url.values["resource_id"] = resource.values["id"]
                        url.save()
                resource.values["update_timestamp"] = t
                resource.values["pending_update"] = 1
                if elem["blocked"]:
                    resource.values["is_tracking"] = 1
                if resource.values["hash"] and not resource.values["file"]:
                    os.makedirs(os.path.join(os.path.abspath("."), temp_folder), exist_ok=True)
                    filename = os.path.join(temp_folder, domain.values["name"] + '.tmp')
                    if download_url(process, url.values["url"], filename):
                        size = os.stat(filename).st_size
                        # Compress the code
                        with open(filename, 'rb') as f:
                            code = f.read()
                        compressed_code = zlib.compress(code)
                        resource.values["file"] = compressed_code
                        resource.values["size"] = size
                        # Compute the fuzzy hash
                        resource.values["fuzzy_hash"] = lsh_file(filename)
                        try:
                            with open(filename, 'r', encoding="utf-8") as f:
                                code = f.read()
                                for collector in collectors:
                                    if collector.values["name"] == "utiq":
                                        false_positives = ["autiqu", "outiqu", "eutiqu", "autiqo", "marutiq"]
                                        found = False
                                        for fp in false_positives:
                                            if re.search(fp, code):
                                                found = True
                                        if not found and re.search("utiq", code):
                                            url.add(collector)
                                    else:
                                        if re.search(collector.values["name"], code):
                                            url.add(collector)
                        except Exception as e:
                            logger.error("[Worker %s] Decoding error: %s" % (process, str(e)))
                    else:
                        logger.error("[Worker %s] Error #1: Resource not correctly saved - %s" % (process, elem["url"]))
                if not resource.save():
                    # Wait until the other thread saves the file inside the database (or 30s max)
                    seconds = 30
                    while not resource.load(elem["hash"]) and seconds > 0:
                        seconds -= 1
                        time.sleep(1)
                # Update the most probable type of the resource:
                # --- Different URLs pointing to the same resource can mark it as different types.
                # --- We set the most prevalent one
                #db.call("ComputeResourceType", values=[resource.values["id"]])
                # TODO: Fix the popularity update DB procedure
                #db.call("ComputeResourcePopularityLevel", values=[resource.values["id"]])

        # json.dump(elem, sys.stdout, indent=2, ensure_ascii=False)

        # Insert the relation between the domain and the URL (including the HTML frame that called it)
        initiator_id = None
        if "originUrl" in elem.keys():
            initiator_frame = Connector(db, "url")
            initiator_frame.load(hash_string(elem["originUrl"]))
            initiator_id = initiator_frame.values["id"]
        domain.add(url, {"third_party": elem["thirdParty"],
                         "initiator_frame": initiator_id,
                         "insert_date": t,
                         "update_timestamp": t})

        ## Automatically label tracking for the url and related resource
        ## Temporarily disabled as it is used onyl for eprivo.eu but not for research purposes
        ## Uncomment next line to enable it
        #check_tracking(url, domain)
    domain.save()


def insert_link(db, parent_url, link_url):
    """ Inserts a new link inside the parent URL """

    url1 = Connector(db, "url")
    url1.load(hash_string(parent_url))
    url2 = Connector(db, "url")
    url2.load(hash_string(link_url))
    if not url1.values["id"] or not url2.values["id"]:
        return False
    link_id = db.custom("SELECT id FROM link WHERE url_id1 = %d AND url_id2 = %d" % (url1.values["id"], url2.values["id"]))
    if not link_id:
        link = Connector(db, "link")
        link.values["url_id1"] = url1.values["id"]
        link.values["url_id2"] = url2.values["id"]
        link.save()
    return True


def parse_internal_links(url, webcode):
    """ Obtains a dictionary with the internal links on the webcode """

    links = []
    soup = BeautifulSoup(webcode, 'lxml')
    for hyperlink in soup.find_all('a'):
        link = hyperlink.get('href')
        if not link:
            continue
        
        # We cut on \# characters to avoid also multiple urls with anchors for the same website
        link = link.split("#")[0]
        
        # If it is a malformed link try to fix it by adding the hosting domain
        if link and link[0] == '/':
            link = url.split(extract_domain(url))[0] + extract_domain(url) + link
        elif link and link[0] != "h" and 1 < len(link.split("/")[0].split(".")) < 4:
            link = "http://" + link
        elif link and link[0:4] != 'http':
            link = url.split(extract_domain(url))[0] + extract_domain(url) + '/' + link
        
        links.append(link)

    return links
        

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
                logger.error("[Worker %s] Error #1: %s" % (process, str(e)))
                return False
        except UnicodeError as e:
            logger.error("[Worker %s] Error #2: Couldn't download url %s with error %s" % (process, url, str(e)))
            return False
        except Exception as e:
            logger.error("[Worker %s] Error #3: %s" % (process, str(e)))
            return False
    logger.debug("[Worker %s] Found external resource %s" % (process, url))
    return True

