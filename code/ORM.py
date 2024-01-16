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
import signal
from datetime import datetime, timezone, timedelta
from multiprocessing import Process, Pool, Queue, cpu_count, Lock, Manager

# Own modules
from db_manager import Db, Connector
from driver_manager import build_driver, visit_site
from data_manager import insert_link
from utils import hash_string

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

    # Load geolocation database
    geo_db = geolocation.Reader(config.GEOCITY_FILE_PATH)

    # Load the selenium driver with proper plugins
    driver = build_driver(cache, update_ublock, process)
    while not driver:
        driver = build_driver(cache, update_ublock, process)
    driver.set_page_load_timeout(30)

    if not driver:
        return 1

    while True:
        try:
            work_queue_lock.acquire()
            work = work_queue.get(block=False)
            site = work[0]
            url = work[1]
            deepness = work[2]
            parent = work[3]
            work_queue_lock.release()
        except queue.Empty:
            work_queue_lock.release()
            status_queue_lock.acquire()
            my_dict = driver.capabilities 
            status_queue.put([str(process), "", os.getpid(), driver.service.process.pid, my_dict['moz:processID'], datetime.now()])
            status_queue_lock.release()
            time.sleep(10)
        except Exception as e:
            logger.error("[Worker %d] %s" % (process, str(e)))
        else:
            status_queue_lock.acquire()
            my_dict = driver.capabilities 
            status_queue.put([str(process), url, os.getpid(), driver.service.process.pid, my_dict['moz:processID'], datetime.now()])
            status_queue_lock.release()
            domain = Connector(db, "domain")
            domain.load(int(site))

            # Launch the crawl
            extra_tries = 3
            completed = False
            repeat = True
            while extra_tries > 0 and not completed and repeat:
                extra_tries -= 1
                driver, completed, repeat, links = visit_site(db, process, driver, domain, url, temp_folder, cache, update_ublock, geo_db)
            if completed:
                if parent:
                    insert_link(db, parent, url)
                if len(links) > 0 and max_deep > deepness:
                    work_queue_lock.acquire()
                    for link in links:
                        if link not in url_list:
                            link_url = Connector(db, "url")
                            if not link_url.load(hash_string(link)):
                                url_list.append(link)
                                work_queue.put([site, link, deepness + 1, url])
                    work_queue_lock.release()
            try:
                url_list.remove(url)
            except Exception as e:
                logger.error("[Main process] Error removing %s from TODO work - %s" % (url, str(e)))



parser = argparse.ArgumentParser(description='Online Resource Mapper (ORM)')
parser.add_argument('-p', dest='processes', type=int, default=0,
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
parser.add_argument('--statusfull', dest='cache', action="store_true",
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
    processes = int(args.processes)
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
    if not processes:
        cpu = cpu_count()
        try:
            available_cpu = len(os.sched_getaffinity(0))
        except Exception as e:
            logger.warning("Platform not recognized. Getting the maximum CPU's")
            available_cpu = cpu
        # Save 1 CPU for other purposes
        if cpu > 1 and cpu == available_cpu:
            processes = cpu - 1
        else:
            processes = available_cpu
    logger.info("Processes to run: %d " % processes)

    # Initialize shared structures
    manager = Manager()
    work_queue = manager.Queue()
    work_queue_lock = Lock()
    status_queue = manager.Queue()
    status_queue_lock = Lock()
    url_list = manager.list([])


    # Create and call the workers
    process_dict = {}
    logger.debug("[Main process] Spawning new workers...")
    for i in range(processes):
        process =  Process(target=main, args=[i])
        process_dict[str(i)] = {"process": process, 
                                "url": "", 
                                "pid": -1, 
                                "geckodriver_pid": -1, 
                                "browser_pid": -1, 
                                "last_message": datetime.now()}
        process.start()

    pending = ["0"]
    last_id = args.start
    while True:
        # Insert new work into queue if needed.
        work_queue_lock.acquire()
        qsize = work_queue.qsize()
        logger.info("[Main process] Queued work %d" % qsize)
        work_queue_lock.release()
        if qsize < (2 * processes):
            logger.debug("[Main process] Getting work")
            now = datetime.now(timezone.utc)
            td = timedelta(-1 * update_threshold)
            period = now + td
            rq = 'SELECT id, name FROM domain'
            if args.priority:
                rq += ' WHERE priority = 1'
            else:
                rq += ' WHERE priority = 0 AND update_timestamp < "%s"' % (period.strftime('%Y-%m-%d %H:%M:%S'))
            rq += ' AND id NOT IN (%s)' % ','.join(pending)
            rq += ' AND id > %s' % last_id
            rq += ' ORDER BY update_timestamp, id ASC LIMIT %d ' % (int(0.5 * processes))
            pending = ["0"]
            database = Db()
            results = database.custom(rq)
            # If no new work wait ten seconds and retry
            if len(results) > 0:
                # Initialize job queue
                logger.debug("[Main process] Enqueuing work")
                work_queue_lock.acquire()
                for result in results:
                    if clean:
                        # Clean the domain info before crawling new info
                        request = "DELETE FROM domain_url WHERE domain_id = %d" % result["id"]
                        database.custom(request)
                    if args.priority:
                        domain = Connector(database, "domain")
                        domain.load(int(result["id"]))
                        domain.values["priority"] = 0
                        domain.values.pop("update_timestamp")
                        domain.save()
                    url = 'http://' + result["name"] +'/'
                    url_list.append(url)
                    work_queue.put([result["id"], url, 0, None])
                    pending.append(str(result["id"]))
                    last_id = int(result["id"])
                work_queue_lock.release()
            database.close()
        
        # Check the processes status
        status_queue_lock.acquire()
        while True:
            try:
                process_status = status_queue.get(block=False)
                process_dict[process_status[0]]["url"] = process_status[1]
                process_dict[process_status[0]]["pid"] = process_status[2]
                process_dict[process_status[0]]["geckodriver_pid"] = process_status[3]
                process_dict[process_status[0]]["browser_pid"] = process_status[4]
                process_dict[process_status[0]]["last_message"] = process_status[-1]
            except queue.Empty:
                break
            except Exception as e:
                logger.error("[Main process] Status queue parsing error: %s" % str(e))
                queue_not_empty = False
        status_queue_lock.release()

        # If some process does not respond for more than 5 minutes kill it and respawn it
        for k in process_dict.keys():
            if process_dict[k]["last_message"] < (datetime.now() - timedelta(minutes=5)):
                # Save the failed URL for postmortem diagnostic
                with open(os.path.join(os.path.abspath("."), "failed_urls.txt"), "a", encoding="utf-8") as f:
                    f.write(process_dict[k]["url"] + "\n")

                # Kill worker as well as its own geckodriver and browser instances
                try:
                    os.kill(process_dict[k]["geckodriver_pid"], signal.SIGKILL)
                except Exception as e:
                    logger.error("[Main process] Error killing process %d: %s)" % (process_dict[k]["geckodriver_pid"], str(e)))
                try:
                    os.kill(process_dict[k]["browser_pid"], signal.SIGKILL)
                except Exception as e:
                    logger.error("[Main process] Error killing process %d: %s)" % (process_dict[k]["browser_pid"], str(e)))
                try:
                    os.kill(process_dict[k]["pid"], signal.SIGKILL)
                except Exception as e:
                    logger.error("[Main process] Error killing process %d: %s)" % (process_dict[k]["pid"], str(e)))

                # Create new worker and launch it
                logger.error("[Main Process] Respawning process %d" % int(k))
                process = Process(target=main, args=[int(k)])
                process_dict[k] = {"process": process, 
                                   "url": "",
                                   "pid": -1, 
                                   "geckodriver_pid": -1, 
                                   "browser_pid": -1, 
                                   "last_message": datetime.now()}
                process.start()
        
        ### TODO: Catch the Ctrl+C hotkey and clean the work queue and cleanly stop the current processes using the process object inside the dict
        time.sleep(5)
    display.stop()