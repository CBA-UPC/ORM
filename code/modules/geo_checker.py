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
from os import listdir
from os.path import isfile, join
import logging
import logging.config
import queue
import zlib
from multiprocessing import Pool, Queue, cpu_count, Lock

# 3rd party modules
from geoip2 import database as geodb

# Own modules
import config
from db_manager import Db, Connector
from utils import extract_location

logging.config.fileConfig('logging.conf')

verbose = {"0": logging.CRITICAL, "1": logging.ERROR, "2": logging.WARNING, "3": logging.INFO, "4": logging.DEBUG}

logger = logging.getLogger("Geo-Checker")


def check_geo(db, url, geoloc):
    """ Inserts the URL data into the database and returns the URL Connector. """

    loc = Connector(db, "location")
    if not loc.load(url.values["id"]):
        loc.values["id"] = url.values["id"]
    location = extract_location(url.values["remote_IP_address"], geoloc)
    for key in location.keys():
        loc.values[key] = location[key]
    loc.save()



parser = argparse.ArgumentParser(description='Geolocation checker')
parser.add_argument('-t', dest='threads', type=int, default=0,
                    help='Number of threads/processes to span (Default: Auto)')
parser.add_argument('-v', dest='verbose', type=int, default=3,
                    help='Verbose: 0=CRITICAL; 1=ERROR; 2=WARNING; 3=INFO; 4=DEBUG (Default: WARNING)')
parser.add_argument('-d', dest='patterns', type=str, default='patterns',
                    help='Folder with the pattern lists (Default: "./patterns"')


def main(process):
    """ Main process in charge of taking work from the queue and extracting info if needed.

    While there is remaining work in the queue continuously passes new jobs until its empty.
    If the 'no-update' argument is false it cleans the previously URL's linked for the current domain. """

    # Load the DB manager for this process
    db = Db()

    # Load the geolocation db
    geolocation = geodb.Reader(config.CITY_FILE_PATH)

    remaining = True
    while remaining:
        try:
            queue_lock.acquire()
            url_id = work_queue.get(False)
            current = work_queue.qsize() + 1
            queue_lock.release()
        except queue.Empty:
            queue_lock.release()
            logger.info("Queue empty (proc. %d)" % process)
            remaining = False
        except Exception as e:
            logger.error("%s (proc. %d)" % (str(e), process))
        else:
            url = Connector(db, "url", log=True)
            url.load(url_id)
            logger.info('Job [%d/%d] %s (proc: %d)' % (total - current, total, url.values["url"], process))
            check_geo(db, url, geolocation)
    db.close()
    return 1


if __name__ == '__main__':
    """ Main process in charge of reading the arguments, filling the work queue and creating the workers."""

    # Take arguments
    args = parser.parse_args()
    threads = args.threads
    pattern_folder = os.path.join(os.path.abspath("."), args.patterns)
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
    rq = "SELECT url.id FROM url ORDER BY url.id"
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
