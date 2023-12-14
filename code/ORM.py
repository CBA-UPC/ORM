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
import argparse
import os
import time
import logging.config
import queue
from datetime import datetime, timezone, timedelta
from multiprocessing import Pool, Queue, cpu_count, Lock

# Own modules
from db_manager import Db, Connector
from driver_manager import build_driver, visit_site

# Third-party modules
from geoip2 import database as geolocation
from pyvirtualdisplay import Display
from setproctitle import setproctitle

import config

logging.config.fileConfig('logging.conf')

verbose = {"0": logging.CRITICAL, "1": logging.ERROR, "2": logging.WARNING, "3": logging.INFO, "4": logging.DEBUG}

logger = logging.getLogger("ORM")


def main(process):
    """ Main process in charge of taking work from the queue and extracting info if needed.

    While there is remaining work in the queue continuously passes new jobs until its empty.
    If the 'no-update' argument is false it cleans the previously URL's linked for the current domain. """

    # Load the DB manager for this process
    db = Db()

    # Load enabled plugins
    plugin_list = Connector(db, "plugin")
    plugin_list = plugin_list.get_all({"enabled": 1})

    # Load geolocation database
    geo_db = geolocation.Reader(config.GEOCITY_FILE_PATH)

    # Load the selenium driver with proper plugins
    driver_list = []
    for plugin in plugin_list:
        driver = build_driver(plugin, cache, update_ublock, process)
        while not driver:
            driver = build_driver(plugin, cache, update_ublock, process)
        driver.set_page_load_timeout(30)
        driver_list.append([driver, plugin])

    if not driver_list:
        return 1

    while True:
        try:
            queue_lock.acquire()
            site = work_queue.get(block=False)
            queue_lock.release()
        except queue.Empty:
            queue_lock.release()
            time.sleep(1)
        except Exception as e:
            logger.error("[Worker %d] %s" % (process, str(e)))
        else:
            domain = Connector(db, "domain")
            domain.load(int(site))
            logger.info('[Worker %d] Domain %s' % (process, domain.values["name"]))
            for driver in driver_list:
                if clean:
                    # Clean the domain info before crawling new info
                    request = "DELETE FROM domain_url WHERE domain_id = %d AND plugin_id = %d" % (domain.values["id"],
                                                                                              driver[1].values['id'])
                    db.custom(request)
                # Launch the crawl
                url = 'http://' + domain.values["name"] +'/'
                extra_tries = 3
                completed = False
                repeat = True
                while extra_tries > 0 and not completed and repeat:
                    extra_tries -= 1
                    driver[0], completed, repeat, link_dict, parsed_links = visit_site(db, process, driver[0], domain, url,
                                                              driver[1], temp_folder, cache, update_ublock, geo_db, 0, max_deep, {})
                # TODO: Try to remove websites when unable to get info??
                #  -> if a connection problem happens all the websites will be removed...


parser = argparse.ArgumentParser(description='Online Resource Mapper (ORM)')
parser.add_argument('-p', dest='threads', type=int, default=0,
                    help='Number of scrape processes to span (Default: Auto)')
parser.add_argument('-v', dest='verbose', type=int, default=3,
                    help='Verbose: 0=CRITICAL; 1=ERROR; 2=WARNING; 3=INFO; 4=DEBUG (Default: INFO)')
parser.add_argument('-t', dest='tmp', type=str, default='tmp',
                    help='Temporary folder (Default: "./tmp"')
parser.add_argument('--deepness', dest='max_deep', type=int, default=0,
                    help='Maximum recursive exploration of website internal links (Default: 0; scan only the homepages)')
parser.add_argument('--start', dest='start', type=int, default=0,
                    help='Domain id start index (Default: 0). Used to skip some domains and start by a especific domain')
parser.add_argument('--clean', dest='clean', action="store_true",
                    help='Cleans the domain info before crawling new info (Default: False)')
parser.add_argument('--statefull', dest='cache', action="store_true",
                    help='Enables cache/cookies (Default: Clear cache/cookies)')
parser.add_argument('--update-threshold', dest='update_threshold', type=int, default=30,
                    help='Period of days to skip rescanning a website (Default: 30 days).')
parser.add_argument('--update-ublock', dest='update_ublock', action="store_true",
                    help='Updates uBlock pattern lists every time a new browser is launched (Default: no update)')
parser.add_argument('--priority-scan', dest='priority', action="store_true",
                    help='Activates priority scan. This ORM will only scan domains with the priority flag enabled')


if __name__ == '__main__':
    """ Main process in charge of reading the arguments, filling the work queue and creating the workers."""

    # Take arguments
    args = parser.parse_args()
    cache = args.cache
    clean = args.clean
    update_ublock = args.update_ublock
    update_threshold = args.update_threshold
    threads = args.threads
    max_deep = args.max_deep
    temp_folder = os.path.join(os.path.abspath("."), args.tmp)
    v = args.verbose
    os.makedirs(os.path.join(os.path.abspath("."), "log"), exist_ok=True)
    if verbose[str(v)]:
        logger.setLevel(verbose[str(v)])

    display = Display(visible=False, size=(1920, 1080))
    display.start()

    # If thread parameter is auto get the (total-1) or the available CPU's, whichever is smaller
    logger.info("Calculating processes...")
    if not threads:
        cpu = cpu_count()
        try:
            available_cpu = len(os.sched_getaffinity(0))
        except Exception as e:
            logger.warning("Platform not recognized. Getting the maximum CPU's")
            available_cpu = cpu
        # Save 1 CPU for other purposes
        if cpu > 1 and cpu == available_cpu:
            threads = cpu - 1
        else:
            threads = available_cpu
    logger.info("Processes to run: %d " % threads)

    # Initialize job queue
    work_queue = Queue()
    queue_lock = Lock()

    # Create and call the workers
    logger.debug("[Main process] Spawning new workers...")
    with Pool(processes=threads) as pool:
        p = pool.map_async(main, [i for i in range(int(threads))])

        pending = ["0"]
        last_id = args.start
        while True:
            # Insert new work into queue if needed.
            queue_lock.acquire()
            qsize = work_queue.qsize()
            queue_lock.release()
            if qsize < (2 * threads):
                logger.debug("[Main process] Getting work")
                now = datetime.now(timezone.utc)
                td = timedelta(-1 * update_threshold)
                period = now + td
                rq = 'SELECT id FROM domain'
                if args.priority:
                    rq += ' WHERE priority = 1'
                else:
                    rq += ' WHERE priority = 0 AND update_timestamp < "%s"' % (period.strftime('%Y-%m-%d %H:%M:%S'))
                rq += ' AND id NOT IN (%s)' % ','.join(pending)
                rq += ' AND id > %s' % last_id
                rq += ' ORDER BY update_timestamp, id ASC LIMIT %d ' % (2 * threads)
                pending = ["0"]
                database = Db()
                results = database.custom(rq)
                # If no new work wait ten seconds and retry
                if len(results) > 0:
                    # Initialize job queue
                    logger.debug("[Main process] Enqueuing work")
                    queue_lock.acquire()
                    for result in results:
                        if args.priority:
                            domain = Connector(database, "domain")
                            domain.load(int(result["id"]))
                            domain.values["priority"] = 0
                            domain.values.pop("update_timestamp")
                            domain.save()
                        work_queue.put(result["id"])
                        pending.append(str(result["id"]))
                        last_id = int(result["id"])
                    queue_lock.release()
                database.close()
            time.sleep(1)
    display.stop()