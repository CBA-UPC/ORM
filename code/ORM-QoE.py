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
from multiprocessing import Pool, Queue, cpu_count, Lock

# Own modules
from db_manager import Db, Connector
from driver_manager import build_driver, visit_site
from utils import hash_string

logging.config.fileConfig('../logging.conf')

verbose = {"0": logging.CRITICAL, "1": logging.ERROR, "2": logging.WARNING, "3": logging.INFO, "4": logging.DEBUG}

logger = logging.getLogger("ORM")


parser = argparse.ArgumentParser(description='Online Resource Mapper (ORM)')
parser.add_argument('-start', dest='start', type=int, default=0, help='Start index (Default: First)')
parser.add_argument('-end', dest='end', type=int, default=-1, help='End index (Default: Last)', nargs='?')
parser.add_argument('-t', dest='threads', type=int, default=0,
                    help='Number of threads/processes to span (Default: Auto)')
parser.add_argument('-v', dest='verbose', type=int, default=3,
                    help='Verbose: 0=CRITICAL; 1=ERROR; 2=WARNING; 3=INFO; 4=DEBUG (Default: WARNING)')
parser.add_argument('-d', dest='tmp', type=str, default='tmp',
                    help='Temporary folder (Default: "./tmp"')
parser.add_argument('--statefull', dest='cache', action="store_true",
                    help='Enables cache/cookies (Default: Clear cache/cookies)')
parser.add_argument('--no-update', dest='no_update', action="store_true",
                    help='Not scraps already scraped domains between the selected range (Default: Update)')


def main(process):
    """ Main process in charge of taking work from the queue and extracting info if needed.

    While there is remaining work in the queue continuously passes new jobs until its empty.
    If the 'no-update' argument is false it cleans the previously URL's linked for the current domain. """

    # Load the DB manager for this process
    db = Db()

    # Load enabled plugins
    plugin_list = Connector(db, "plugin")
    plugin_list = plugin_list.get_all({"enabled": 1})

    # Load the selenium driver with proper plugins
    driver_list = []
    for plugin in plugin_list:
        driver = build_driver(plugin, cache, process)
        while not driver:
            driver = build_driver(plugin, cache, process)
        driver.set_page_load_timeout(30)
        driver_list.append([driver, plugin])

    if not driver_list:
        return 1

    remaining = True
    while remaining:
        try:
            queue_lock.acquire()
            site = work_queue.get(False)
            current = work_queue.qsize() + 1
            queue_lock.release()
        except queue.Empty:
            queue_lock.release()
            logger.info("Queue empty (proc. %d)" % process)
            remaining = False
        except Exception as e:
            logger.error("%s (proc. %d)" % (str(e), process))
        else:
            domain = Connector(db, "domain")
            domain.load(site)
            document = Connector(db, "type")
            document.load(hash_string("Document"))
            urls = domain.get("url", order="url_id")
            present = False
            for url in urls:
                if url.values["type"] == document.values["id"]:
                    present = True
            if present and no_update:
                continue
            logger.info('Job [%d/%d] %s (proc: %d)' % (total - current, total, domain.values["name"], process))
            for driver in driver_list:
                url_property = {"plugin_id": driver[1].values['id']}
                urls = domain.get("url", order="url_id", args=url_property)
                for url in urls:
                    domain.remove(url)
                driver[0], failed = visit_site(db, process, driver[0], domain, driver[1], temp_folder, cache)
                # Clean the domain results if crawl failed
                if failed:
                    urls = domain.get("url", order="url_id", args=url_property)
                    for url in urls:
                        domain.remove(url)
                    break
            # TODO: Clean the urls/resources that are not used by any domain anymore.
            # work_queue.task_done()
    db.close()
    for driver in driver_list:
        driver[0].close()
    return 1


if __name__ == '__main__':
    """ Main process in charge of reading the arguments, filling the work queue and creating the workers."""

    # Take arguments
    args = parser.parse_args()
    cache = args.cache
    no_update = args.no_update
    threads = args.threads
    temp_folder = os.path.join(os.path.abspath("."), args.tmp)
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
    rq = "SELECT domain.id FROM domain"
    if args.start > 0:
        rq += " WHERE domain.id > %d" % (args.start - 1)
        if args.end > 0:
            rq += " AND domain.id < %d" % (args.end + 1)
    elif args.end > 0:
        rq += " WHERE domain.id < %d" % (args.end + 1)
    rq += " ORDER BY domain.id"
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
