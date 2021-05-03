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
import argparse
import os
import logging.config
import queue
import zlib
from multiprocessing import Pool, Queue, cpu_count, Lock
from ast import literal_eval

import jsbeautifier
from bs4 import BeautifulSoup, UnicodeDammit
from w3lib.encoding import html_to_unicode
from rabin import get_file_fingerprints, set_min_block_size, set_max_block_size, set_average_block_size

# Own modules
from db_manager import Db, Connector
from utils import utc_now

logging.config.fileConfig('logging.conf')

verbose = {"0": logging.CRITICAL, "1": logging.ERROR, "2": logging.WARNING, "3": logging.INFO, "4": logging.DEBUG}

logger = logging.getLogger("MODULE")

set_max_block_size(4096)
set_min_block_size(64)
set_average_block_size(512)


def beautify_code(process, code, headers):
    """ Beautifies the code whenever possible. """

    # TODO: Fix beautify_code bug (freezes with some js code e.g. pinterest.com)
    if not isinstance(code, str):
        if headers and "content-type" in headers.keys():
            ct = headers["content-type"]
        else:
            ct = None
        detected_encoding, html_content_unicode = html_to_unicode(
            content_type_header=ct,
            html_body_str=code,
            auto_detect_fun=lambda x: UnicodeDammit(x).original_encoding,
        )
    else:
        html_content_unicode = code
    try:
        code = jsbeautifier.beautify(html_content_unicode)
    except Exception as e:
        logger.info("(proc. %d) Encoding error: %s" % (process, str(e)))
        code = html_content_unicode
    return code


def extract_scripts(process, resource, folder, headers):
    """ Extract the embedded scripts and calls the function to insert fingerprints into the database. """

    try:
        page_source = zlib.decompress(resource.values["file"])
        soup = BeautifulSoup(page_source, 'lxml')
        for script_code in soup.find_all('script', {"src": False}):
            temp_filename = os.path.join(os.path.abspath("."), folder, resource.values["hash"] + ".tmp")
            os.makedirs(os.path.join(os.path.abspath("."), folder), exist_ok=True)
            code = script_code.text
            code = beautify_code(process, code, headers)
            with open(temp_filename, 'wb') as f:
                f.write(code.encode('utf-8'))
            compute_fingerprints(resource, temp_filename)
    except:
        logger.info('[Worker %d] Could not parse HTML. Assuming JavaScript' % process)
        try:
            url_headers = None
            request = "SELECT id FROM url WHERE resource_id = %d AND response_headers IS NOT NULL LIMIT 1" % resource.values["id"]
            res = resource.db.custom(request)
            for r in res:
                url = Connector(resource.db, "url")
                url.load(r["id"])
                url_headers = url.values["response_headers"]
            code = zlib.decompress(resource.values["file"])
            code = beautify_code(process, code, url_headers)
            os.makedirs(os.path.join(os.path.abspath("."), temp_folder), exist_ok=True)
            temp_filename = os.path.join(os.path.abspath("."), temp_folder, resource.values["hash"] + ".tmp")
            with open(temp_filename, 'wb') as f:
                f.write(code.encode('utf-8', 'replace'))
            compute_fingerprints(resource, temp_filename)
        except:
            logger.warning('[Worker %d] Could not compute fingerprint' % process)
        return False
    return True


def compute_fingerprints(resource, temp_filename):
    """ Computes the fingerprints for the given resource. """

    fingerprints = get_file_fingerprints(temp_filename)
    t = utc_now()
    for j in range(len(fingerprints)):
        fp = str(fingerprints[j][2])
        fingerprint = Connector(resource.db, "fingerprint")
        if not fingerprint.load(fp):
            fingerprint.values.pop('tracking_probability', None)
            fingerprint.values.pop('dirt_level', None)
            fingerprint.values["insert_date"] = t
            fingerprint.values["update_timestamp"] = t
            if not fingerprint.save():
                fingerprint.load(fp)
        resource.add(fingerprint, {"offset": fingerprints[j][0], "length": fingerprints[j][1]})
        #resource.db.call("ComputeFingerprintDirtLevel", values=[fingerprint.values["id"]])
        #resource.db.call("ComputeFingerprintPopularityLevel", values=[fingerprint.values["id"]])
    os.remove(temp_filename)


parser = argparse.ArgumentParser(description='Pattern matching list checker')
parser.add_argument('-t', dest='threads', type=int, default=0,
                    help='Number of threads/processes to span (Default: Auto)')
parser.add_argument('-start', dest='start', type=int, default=0, help='Start index (Default: First)')
parser.add_argument('-end', dest='end', type=int, default=-1, help='End index (Default: Last)', nargs='?')
parser.add_argument('-v', dest='verbose', type=int, default=3,
                    help='Verbose: 0=CRITICAL; 1=ERROR; 2=WARNING; 3=INFO; 4=DEBUG (Default: WARNING)')
parser.add_argument('-d', dest='folder', type=str, default='tmp',
                    help='Temporary folder (Default: "./tmp"')


def main(process):
    """ Main process in charge of taking work from the queue and extracting info if needed.

    While there is remaining work in the queue continuously passes new jobs until its empty.
    If the 'no-update' argument is false it cleans the previously URL's linked for the current domain. """

    # Load the DB manager for this process
    db = Db()

    remaining = True
    while remaining:
        try:
            queue_lock.acquire()
            resource_id = work_queue.get(False)
            current = work_queue.qsize() + 1
            queue_lock.release()
        except queue.Empty:
            queue_lock.release()
            logger.info("Queue empty (proc. %d)" % process)
            remaining = False
        except Exception as e:
            logger.error("%s (proc. %d)" % (str(e), process))
        else:
            resource = Connector(db, "resource")
            resource.load(resource_id)
            logger.info('Job [%d/%d] %s (proc: %d)' % (total - current + 1, total, resource.values["hash"], process))

            # Get url headers to pass to Beautiful Soup
            url_headers = None
            request = "SELECT id FROM url WHERE resource_id = %d AND response_headers IS NOT NULL LIMIT 1" % resource_id
            res = db.custom(request)
            for r in res:
                url = Connector(db, "url")
                url.load(r["id"])
                url_headers = literal_eval(url.values["response_headers"])

            if extract_scripts(process, resource, temp_folder, url_headers):
                resource.values["fingerprinted"] = 1
                resource.save()
    db.close()
    return 1


if __name__ == '__main__':
    """ Main process in charge of reading the arguments, filling the work queue and creating the workers."""

    # Take arguments
    args = parser.parse_args()
    threads = args.threads
    temp_folder = os.path.join(os.path.abspath("."), args.folder)
    v = args.verbose
    if verbose[str(v)]:
        logger.setLevel(verbose[str(v)])

    # If thread parameter is auto get the (total-1) or the available CPU's, whichever is smaller
    logger.info("Calculating processes...")
    if not threads:
        cpu = cpu_count()
        try:
            available_cpu = len(os.sched_getaffinity(0))
        except Exception as e:
            logger.warning("Platform not recognized. Getting the maximum CPU's")
            available_cpu = cpu
        if cpu > 1 and cpu == available_cpu:
            threads = cpu - 1
        else:
            threads = available_cpu
    logger.info("Processes to run: %d " % threads)

    # Get domains between the given range from the database.
    logger.info("Getting work")
    database = Db()
    rq = 'SELECT id, type, file FROM resource WHERE fingerprinted = 0 AND size > 0 '
    rq += ' AND type IN ("frame", "script")'
    if args.start > 0:
        rq += " AND id > %d" % (args.start - 1)
    if args.end > 0:
        rq += " AND id < %d" % (args.end + 1)
    rq += ' ORDER BY id'
    results = database.custom(rq)
    total = len(results)
    logger.info("Gotten %d jobs to enqueue" % total)

    # Initialize job queue
    logger.info("Enqueuing work")
    work_queue = Queue()
    queue_lock = Lock()
    for result in results:
        work_queue.put(result["id"])
    database.close()

    # Create and call the workers
    logger.info("Opening workers")
    with Pool(processes=threads) as pool:
        pool.map(main, [i for i in range(threads)])
