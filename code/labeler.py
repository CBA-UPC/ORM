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
import logging
import logging.config
import queue
from multiprocessing import Pool, Queue, cpu_count, Lock

# Own modules
import config
from db_manager import Db, Connector

logging.config.fileConfig('../logging.conf')

verbose = {"0": logging.CRITICAL, "1": logging.ERROR, "2": logging.WARNING, "3": logging.INFO, "4": logging.DEBUG}

logger = logging.getLogger("MODULE")


def check_patterns(resource):
    request = "SELECT DISTINCT url_id FROM domain_url WHERE resource_id = %d ORDER BY url_id" % \
              resource.values["id"]
    res = resource.db.custom(request)

    # get pattern files which URL matches
    for r in res:
        url = Connector(resource.db, "url")
        url.load(r["url_id"])
        pats = url.get("pattern", order="pattern_id")
        if len(pats) > 0:
            return True
    return False


def check_adblockers(resource):
    request = "SELECT DISTINCT plugin_id FROM domain_url WHERE plugin_id > 1 AND resource_id = %d" % \
              resource.values["id"]
    res = resource.db.custom(request)

    # get pattern files which URL matches
    if len(res) > 0:
        return False
    return True


def check_adblockers_urls(resource):
    request = "SELECT DISTINCT url_id FROM domain_url WHERE resource_id = %d ORDER BY url_id" % \
              resource.values["id"]
    res = resource.db.custom(request)

    # get pattern files which URL matches
    for r in res:
        request2 = "SELECT DISTINCT plugin_id FROM domain_url WHERE plugin_id > 1 AND url_id = %d" % r["url_id"]
        res2 = resource.db.custom(request2)
        if len(res2) == 0:
            return True
    return False


parser = argparse.ArgumentParser(description='Pattern matching list checker')
parser.add_argument('-t', dest='threads', type=int, default=0,
                    help='Number of threads/processes to span (Default: Auto)')
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
            logger.info('Job [%d/%d] %s (proc: %d)' % (total - current, total, resource.values["hash"], process))
            last_plugin = 0
            plugins = Connector(db, "plugin")
            plugins = plugins.get_all()
            for plugin in plugins:
                if plugin.values["enabled"] and plugin.values["id"] > last_plugin:
                    last_plugin = plugin.values["id"]
            if check_patterns(resource):
                resource.values["is_tracking"] = 1
                resource.save()
            elif last_plugin > 1 and check_adblockers(resource):
                if check_adblockers_urls(resource):
                    resource.values["is_tracking"] = 1
                    resource.save()


if __name__ == '__main__':
    """ Main process in charge of reading the arguments, filling the work queue and creating the workers."""

    # Take arguments
    args = parser.parse_args()
    threads = args.threads
    temp_folder = os.path.join(os.path.abspath("modules"), args.folder)
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
    rq = "SELECT resource.id FROM resource ORDER BY resource.id"
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
