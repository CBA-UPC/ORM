import os
import re
import mmap
import argparse
import logging.config
import queue
import zlib
from multiprocessing import Pool, Queue, cpu_count, Lock

# Own modules
from db_manager import Db, Connector
from utils import hash_string

logging.config.fileConfig('logging.conf')

verbose = {"0": logging.CRITICAL, "1": logging.ERROR, "2": logging.WARNING, "3": logging.INFO, "4": logging.DEBUG}

logger = logging.getLogger("MODULE")

mouseEvents = ["scroll", "click", "dbclick", "drag", "dragend", "dragstart", "dragleave", "dragover", "drop", "mousedown",
               "mouseenter", "mouseleave", "mousemove", "mouseover", "mouseout", "mouseup", "mousewheel", "wheel"]

tracking_domains = ["clicktale.com", "clicktale.net", "etracker.com", "clickmap.ch", "script.crazyegg.com",
                    "tracking.crazyegg.com", "hotjar.com", "mouseflow.com"]


def find_end(javascript_file, a, ini_label, end_label):
    with open(javascript_file) as f:
        f.seek(a)
        nothing = 0
        while f.read(1) != ini_label:
            nothing += 1
            if nothing == 100:
                return 0
        val = 0
        end = False
        while not end:
            curr = f.read(1)
            if curr == ini_label:
                val += 1
            elif curr == end_label:
                if val == 0:
                    end = True
                    pos = f.tell()
                else:
                    val -= 1
    return pos


def ret_post(javascript_file, ini, end):
    with open(javascript_file) as f:
        s = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        for tag in ['return', 'post', 'postMessage', 'sendMessage', 'ym']:
            ba = bytearray()
            ba.extend(map(ord, tag))
            try:
                if s.find(ba, ini, end) != -1:
                    return True
            except OverflowError as err:
                print("File too large")


def scan(javascript_file):
    done = False
    with open(javascript_file) as f:
        try:
            html = f.read(len("<!DOCTYPE html>"))
            f.seek(0)
            if "<!" in html:
                return False
        except UnicodeDecodeError as e:
            print("Probably not an UTF-8 file")
            return False
        f.seek(0)
        s = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        for event in mouseEvents:
            b = bytearray()
            c = bytearray()
            d = bytearray()
            e = bytearray()
            find = 'addEventListener("' + event + '"'
            find1 = 'on' + event
            find2 = 'ga('
            find3 = 'logEvent'
            b.extend(map(ord, find))
            c.extend(map(ord, find1))
            d.extend(map(ord, find2))
            e.extend(map(ord, find3))
            try:
                org_point = s.find(b)
                org_point1 = s.find(c)
                org_point2 = s.find(d)
                org_point3 = s.find(e)
            except OverflowError as err:
                print("File too large")
            if org_point != -1:
                org_point = f.seek(org_point + len(find))
                f.read(1)
                a = f.tell()
                if f.read(1) != " ":
                    f.seek(a)
                name = ""
                if f.read(len("function(")) == "function(":
                    point = f.tell()
                    pos = find_end(javascript_file, f.tell(), '{', '}')
                    done = done or ret_post(javascript_file, point, pos)
                else:
                    f.seek(org_point)
                    f.read(1)
                    curr = f.read(1)
                    while curr != "," and curr != '(' and curr != ";":
                        if curr == '.':
                            name = ""
                        elif curr != ' ':
                            name += curr
                        curr = f.read(1)
                    if "fireAnalytics" in name:
                        return True, 0
                    b = bytearray()
                    find = "function " + name
                    b.extend(map(ord, find))
                    try:
                        point = s.find(b)
                    except OverflowError as err:
                        print("File too large")
                    if point != -1:
                        point = f.seek(point + len(find))
                        pos = find_end(javascript_file, point, "{", "}")
                        f.seek(pos)
                        done = done or ret_post(javascript_file,point,pos)
            if not done and org_point1 != -1:
                org_point1 = f.seek(org_point1 + len(find1))
                if f.read(1) != " ":
                    f.seek(org_point1)
                aux = f.read(1)
                if aux == "=":
                    pos_aux = f.tell()
                    if f.read(1) != " ":
                        f.seek(pos_aux)
                    if f.read(len("function(")) == "function(":
                        pos = find_end(javascript_file, pos_aux, "{", "}")
                        done = done or ret_post(javascript_file, pos_aux, pos)
                    else:
                        f.seek(pos_aux)
                        if f.read(1) == "\"":
                            while f.read(1) != "\"":
                                nothing = 0
                            pos = f.tell()
                            done = done or ret_post(javascript_file, pos_aux, pos)
                        else:
                            f.seek(pos_aux)
                            curr = f.read(1)
                            name = curr
                            while curr != "," and curr != '(' and curr != ";":
                                if curr == '.':
                                    name = ""
                                elif curr != ' ':
                                    name += curr
                                curr = f.read(1)
                            c = bytearray()
                            find1 = "function " + name
                            c.extend(map(ord, find))
                            try:
                                point = s.find(c)
                            except OverflowError as err:
                                print("File too large")
                            if point != -1:
                                point = f.seek(point + len(find))
                                pos = find_end(javascript_file, point, "{", "}")
                                done = done or ret_post(javascript_file, point, pos)
                elif aux == "(":
                    pos = find_end(javascript_file, org_point1, "{", "}")
                    done = done or ret_post(javascript_file, org_point1, pos)
            if not done and org_point2 != -1:
                point = f.seek(org_point2 + len(find2)-1)
                pos = find_end(javascript_file, point, "(", ")")
                f.seek(pos)
                d = bytearray()
                d.extend(map(ord, event))
                try:
                    ret = s.find(d, point, pos)
                except OverflowError as err:
                    print("File too large")
                if ret != -1:
                    return True
                d = bytearray()
                d.extend(map(ord, 'on' + event))
                try:
                    ret = s.find(d, point, pos)
                except OverflowError as err:
                    print("File too large")
                if ret != -1:
                    return True
            if not done and org_point3 != -1:
                point = f.seek(org_point2 + len(find3))
                pos = find_end(javascript_file, point, "(", ")")
                f.seek(pos)
                d = bytearray()
                d.extend(map(ord, event))
                try:
                    ret = s.find(d, point, pos)
                except OverflowError as err:
                    print("File too large")
                if ret != -1:
                    return True
    return done


parser = argparse.ArgumentParser(description='Mouse tracking detector')
parser.add_argument('-t', dest='threads', type=int, default=0,
                    help='Number of threads/processes to span (Default: Auto)')
parser.add_argument('-start', dest='start', type=int, default=0, help='Start index (Default: First)')
parser.add_argument('-end', dest='end', type=int, default=-1, help='End index (Default: Last)', nargs='?')
parser.add_argument('-v', dest='verbose', type=int, default=3,
                    help='Verbose: 0=CRITICAL; 1=ERROR; 2=WARNING; 3=INFO; 4=DEBUG (Default: WARNING)')
parser.add_argument('--url', dest='url', action='store_true', help='Look for url patterns instead js files')


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
            element_id = work_queue.get(False)
            current = work_queue.qsize() + 1
            queue_lock.release()
        except queue.Empty:
            queue_lock.release()
            logger.info("Queue empty. (proc. %d)" % process)
            remaining = False
        except Exception as e:
            logger.error("%s (proc. %d)" % (str(e), process))
        else:
            if args.url:
                logger.info('Job [%d/%d] Resource %s (proc: %d)' % (total - current, total, element_id, process))
                url = Connector(db, "url")
                url.load(element_id)
                for domain in tracking_domains:
                    if re.search(domain, url.values["url"]):
                        logger.debug('Found mouse tracking at url %d (proc: %d)' % (element_id, process))
                        tracking = Connector(db, "tracking")
                        tracking.load(hash_string("Mouse tracking"))
                        url.add(tracking)
            else:
                logger.info('Job [%d/%d] Resource %s (proc: %d)' % (total - current, total, element_id, process))
                resource = Connector(db, "resource")
                resource.load(element_id)
                code = zlib.decompress(resource.values["file"])
                tmp_filename = os.path.join(os.path.abspath("."), "tmp", "temp_file_%d.js" % process)
                with open(tmp_filename, "wb") as js_file:
                    js_file.write(code)
                try:
                    tracker = scan(tmp_filename)
                except UnicodeDecodeError as e:
                    print("Probably not an UTF-8 file")
                else:
                    if tracker:
                        logger.debug('Found mouse tracking at resource %d (proc: %d)' % (element_id, process))
                        tracking = Connector(db, "tracking")
                        tracking.load(hash_string("Mouse tracking"))
                        resource.add(tracking)
                os.remove(tmp_filename)
    db.close()
    return 1


if __name__ == '__main__':
    """ Main process in charge of reading the arguments, filling the work queue and creating the workers."""

    # Take arguments
    args = parser.parse_args()
    threads = args.threads
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

    logger.info("Getting work")
    database = Db()
    # Get resources between the given range from the database.
    rq = 'SELECT id FROM resource WHERE size > 0 AND type = "script"'
    if args.url:
        # Get urls between the given range from the database.
        rq = 'SELECT id FROM url WHERE id >= 0'
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
