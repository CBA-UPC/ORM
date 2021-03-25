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
from driver_manager_custom import build_driver, visit_site
from utils import hash_string

logging.config.fileConfig('../logging.conf')

verbose = {"0": logging.CRITICAL, "1": logging.ERROR, "2": logging.WARNING, "3": logging.INFO, "4": logging.DEBUG}

logger = logging.getLogger("ORM")


parser = argparse.ArgumentParser(description='Online Resource Mapper (ORM)')
parser.add_argument('-start', dest='start', type=int, default=0, help='Start index (Default: First)')
parser.add_argument('-end', dest='end', type=int, default=-1, help='End index (Default: Last)', nargs='?')
parser.add_argument('-t', dest='threads', type=int, default=0,
                    help='Number of threads/processes to span (Default: Auto)')
parser.add_argument('-r', dest='repetitions', type=int, default=5, help='Performance check repetitions (Default: 5)')
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
    plugin = Connector(db, "plugin")
    plugin.load(6)

    # Load the selenium driver with proper plugins
    driver, port = build_driver(plugin, cache, process)
    while not driver:
        driver, port = build_driver(plugin, cache, process)
    driver.set_page_load_timeout(30)

    if not driver:
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
            logger.info('Job [%d/%d] %s (proc: %d)' % (total - current, total, domain.values["name"], process))
            total_failed = 0
            total_cleared = 0
            for i in range(repetitions):
                if total_cleared >= 5:
                    continue
                driver, failed = visit_site(db, process, driver, port, domain, plugin, temp_folder, cache)
                if failed:
                    total_failed += 1
                else:
                    total_cleared += 1
                if total_failed > repetitions - 5:
                    db.custom("DELETE from QoE WHERE domain_id = %d" % domain.values["id"])
                    break
            # work_queue.task_done()
    db.close()
    driver.close()
    return 1


if __name__ == '__main__':
    """ Main process in charge of reading the arguments, filling the work queue and creating the workers."""

    # Take arguments
    args = parser.parse_args()
    cache = args.cache
    no_update = args.no_update
    threads = args.threads
    repetitions = args.repetitions
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
    rq = "SELECT DISTINCT domain_id AS id FROM QoE"
    if no_update:
        rq += " WHERE domain_id NOT IN (SELECT DISTINCT domain_id FROM QoE WHERE plugin_id > 5)"
    else:
        rq += " WHERE domain_id >= 0"
    if args.start > 0:
        rq += " AND domain_id >= %d" % args.start
    if args.end > 0:
        rq += " AND domain_id < %d" % (args.end + 1)
    rq += " ORDER BY domain_id"
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
