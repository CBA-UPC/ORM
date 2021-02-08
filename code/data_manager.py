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

# 3rd party modules
import requests
from asn1crypto import pem

# Own modules
from db_manager import Db, Connector
from utils import download_file, hash_file, lsh_file, hash_string, utc_now
from utils import certificate_to_json, extract_location

logging.config.fileConfig('logging.conf')

logger = logging.getLogger("DATA_MANAGER")


def manage_requests(db, process, domain, request_list, plugin, temp_folder, geo_db):
    """ Inserts the URL data if non-existent and downloads resources if needed """

    t = utc_now()

    # Clean malformed URL info groups
    # TODO: Check the reason for the malformed ones
    keys_to_delete = []
    for key in request_list.keys():
        elem = json.loads(request_list[key])
        if not isinstance(elem, dict) or "requestId" not in elem.keys():
            keys_to_delete.append(key)
            logger.info("(proc. %s) : URL details not present - %s" % (process, key))
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
                os.remove(os.path.join(temp_folder, domain.values["name"] + ".pem"))
                certificate.values["json"] = json.dumps(certificate_json)
                if not certificate.save():
                    certificate.load(certificate_hash)
            security_info.pop("certificates")
            url_info["certificate"] = certificate.values["id"]
        url_info["security_info"] = security_info
        url_dict.append(url_info)

    # Insert URL info
    # We sort them by request id and timestamp to link parent urls with child ones
    for elem in sorted(url_dict, key=lambda i: (int(i["requestId"]), int(i["timeStamp"]))):
        url = Connector(db, "url")
        # If not previously seen URL insert it
        if not url.load(hash_string(elem["url"])):
            url.values["url"] = elem["url"]
            url.values["method"] = elem["method"]
            url.values["type"] = elem["type"]
            if elem["blocked"] == "true":
                url.values["blocked"] = 1
            if "from_cache" in elem.keys():
                url.values["from_cache"] = elem["from_cache"]
            if not url.values["from_cache"] and "server_ip" in elem.keys():
                url.values["server_ip"] = elem["server_ip"]
                location = extract_location(url.values["server_ip"], geo_db)
                if location["is_EU"]:
                    url.values["is_EU"] = 1
                url.values["country_code"] = location["country_code"]
            if "request_headers" in elem.keys():
                url.values["request_headers"] = json.dumps(elem["request_headers"])
            content_type = Connector(db, "mime_type")
            if "response_headers" in elem.keys():
                url.values["response_headers"] = json.dumps(elem["response_headers"])
                if "content-type" in elem["response_headers"]:
                    if not content_type.load(hash_string(elem["response_headers"]["content-type"].split(";")[0])):
                        content_type.values["name"] = elem["response_headers"]["content-type"].split(";")[0]
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
                    if elem["blocked"] == "true":
                        resource.values["is_tracking"] = True
                    resource.values["insert_date"] = t
                    resource.values["update_timestamp"] = t
                    if not resource.save():
                        resource.load(elem["hash"])
                url.values["resource_id"] = resource.values["id"]
            url.values["insert_date"] = t
            url.values["update_timestamp"] = t
            url.save()
        else:
            # I URL has already been found update the timestamp
            url.values["update_timestamp"] = t
            url.save()
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
                        if elem["blocked"] == "true":
                            resource.values["is_tracking"] = True
                        resource.values["insert_date"] = t
                        resource.values["update_timestamp"] = t
                        if not resource.save():
                            resource.load(elem["hash"])
                        url.values["resource_id"] = resource.values["id"]
                        url.save()
                resource.values["update_timestamp"] = t
                if elem["blocked"] == "true":
                    resource.values["is_tracking"] = True
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
                        os.remove(filename)
                    else:
                        logger.error("(proc. %s) Error #1: Resource not correctly saved - %s" % (process, elem["url"]))
                if not resource.save():
                    # Wait until the other thread saves the file inside the database (or 30s max)
                    seconds = 30
                    while not resource.load(elem["hash"]) and seconds > 0:
                        seconds -= 1
                        time.sleep(1)
                # Update the most probable type of the resource:
                # --- Different URLs pointing to the same resource can mark it as different types.
                # --- We set the most prevalent one
                db.call("ComputeResourceType", values=[resource.values["id"]])
                # TODO: Fix the popularity update DB procedure
                #db.call("ComputeResourcePopularityLevel", values=[resource.values["id"]])

        # json.dump(elem, sys.stdout, indent=2, ensure_ascii=False)

        # Insert the relation between the domain and the URL (including the HTML frame that called it)
        initiator_id = None
        if "originUrl" in elem.keys():
            initiator_frame = Connector(db, "url")
            initiator_frame.load(hash_string(elem["originUrl"]))
            initiator_id = initiator_frame.values["id"]
        domain.add_double(url, plugin, {"third_party": elem["thirdParty"],
                                        "initiator_frame": initiator_id,
                                        "insert_date": t,
                                        "update_timestamp": t})


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

