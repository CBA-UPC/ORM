# Basic modules
import os
import re
import json
import logging
import logging.config
import argparse
import zlib
import mmap
import time
from datetime import datetime, timezone, timedelta
import queue
from multiprocessing import Pool, Queue, cpu_count, Lock

# 3rd party modules
# from dateutil import parser
from setproctitle import setproctitle

# Own modules
from db_manager import Db, Connector
from utils import hash_string, utc_now, extract_domain
from mouse_code import parser, analyzer


logging.config.fileConfig('logging.conf')

logger = logging.getLogger("TRACKING_MANAGER")

current_timestamp = datetime.now(timezone(timedelta(hours=2), name="UTC+2"))


def check_mouse_tracking(url, domain):
    db = url.db
    resource = Connector(db, "resource")
    resource.load(url.values["resource_id"])
    if not resource.values["file"]:
        return False
        
    try:
        code = zlib.decompress(resource.values["file"])
        success, result = parser.parse(code.decode('utf-8'), False)
        if not success:
            logger.info("Mouse tracking parser error for %s: %s" % (url.values["hash"], result))
            return False
        contents, nodes = result
        success, result = analyzer.analyze(contents, nodes, False)
        if not success:
            logger.info("Mouse tracking analyzer error for %s: %s" % (url.values["hash"], result))
            return False

        if len(result) != 0:
            with open('mouse_results_all.txt', 'a') as file:
                file.write(url.values["hash"].ljust(20) + ';'.join(result) + '\n')

            suspicious = [str((node1, node2, dist, susp)) for (node1, node2, dist, susp) in result if susp]
            if len(suspicious) != 0:
                with open('mouse_results_suspicious.txt', 'a') as file:
                    file.write(url.values["hash"].ljust(20) + ';'.join(suspicious) + '\n')

            return True

    except UnicodeDecodeError as e:
        # Probably not an UTF-8 file
        return False

    except Exception as e:
        logger.info("Mouse tracking exception for %s: %s" % (url.values["hash"], str(e)))
        return False


def main(process):
    """ Main process in charge of taking work from the queue and extracting info if needed.

    While there is remaining work in the queue continuously passes new jobs until its empty.
    If the 'no-update' argument is false it cleans the previously URL's linked for the current domain. """

    # Load the DB manager for this process
    db = Db()

    while True:
        try:
            queue_lock.acquire()
            site = work_queue.get(False)
            queue_lock.release()
        except queue.Empty:
            queue_lock.release()
            #exit(0)
        except Exception as e:
            logger.error("[Worker %d] %s" % (process, str(e)))
        else:
            domain = Connector(db, "domain")
            domain.load(site)
            setproctitle("ORM - Worker #%d - %s" % (process, domain.values["name"]))
            logger.info('[Worker %d] Domain %s' % (process, domain.values["name"]))
            url_list = domain.get("url", order="url_id")
            for url in url_list:
                resource = Connector(db, "resource")
                resource.load(url.values["resource_id"])
                if int(resource.values["size"]) > 0:
                    logger.info('[Worker %d] Domain %s URL %s' % (process, domain.values["name"], url.values["url"]))
                    check_mouse_tracking(url, domain)


argument_parser = argparse.ArgumentParser(description='Tracking parser')
argument_parser.add_argument('-t', dest='threads', type=int, default=0,
                    help='Number of threads/processes to span (Default: Auto)')
argument_parser.add_argument('-start', dest='current', type=int, default=0,
                    help='Id for the starting domain (Default: 0).')
argument_parser.add_argument('-end', dest='end', type=int, default=0,
                    help='Id for the starting domain (Default: All).')

if __name__ == '__main__':
    """ Main process """

    # Take arguments
    args = argument_parser.parse_args()
    threads = args.threads
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
    logger.info("[Main process] Spawning new workers...")
    with Pool(processes=threads) as pool:
        p = pool.map_async(main, [i for i in range(int(threads))])

        pending = ["0"]
        current = int(args.current)
        while True:
            # Insert new work into queue if needed.
            queue_lock.acquire()
            qsize = work_queue.qsize()
            queue_lock.release()
            if qsize < (2 * threads):
                logger.info("[Main process] Getting work")
                rq = 'SELECT id FROM domain'
                rq += ' WHERE id > %d' % current
                if args.end > 0:
                   rq += ' AND id <= %d' % args.end
                rq += ' AND id NOT IN (%s)' % ','.join(pending)
                rq += ' ORDER BY id ASC LIMIT %d ' % (2 * threads)
                pending = ["0"]
                database = Db()
                results = database.custom(rq)
                database.close()
                # If no new work wait ten seconds and retry
                if len(results) > 0:
                    # Initialize job queue
                    logger.info("[Main process] Enqueuing work")
                    queue_lock.acquire()
                    for result in results:
                        work_queue.put(result["id"])
                        pending.append(str(result["id"]))
                        current = result["id"]
                    queue_lock.release()
            time.sleep(1)


