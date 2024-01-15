import os
import argparse
import queue
import zlib
from db_manager import Db, Connector
from multiprocessing import Pool, Queue, cpu_count, Lock

def main(process):
    """ Main process in charge of taking work from the queue and extracting info if needed.

    While there is remaining work in the queue continuously passes new jobs until its empty. """

    # Load the DB manager for this process
    db = Db()

    while True:
        try:
            queue_lock.acquire()
            id = int(work_queue.get(block=True))
            queue_lock.release()
        except queue.Empty:
            queue_lock.release()
            exit(0)
        except Exception as e:
            print("[Worker %d] %s" % (process, str(e)))
        else:
            resource = Connector(db, "resource")
            resource.load(id)
            if not resource.values["file"]:
                print("Resource %d not present in DB" % id)
                continue
            print("Extracting resource %d" % id)
            os.makedirs(folder, exist_ok=True)
            new_file = os.path.join(folder, str(id) + ".js")
            if os.path.isfile(new_file):
                continue
            with open(new_file, "wb") as rfile:
                rfile.write(zlib.decompress(resource.values["file"]))


parser = argparse.ArgumentParser(description='Online Resource Mapper (ORM)')
parser.add_argument('csv', type=str, default="resources.csv",
                    help='CSV/txt file containing the resource id list to extract with one id per line. (Default: resources.csv)')
parser.add_argument('-p', dest='threads', type=int, default=0,
                    help='Number of processes to span (Default: Auto)')
parser.add_argument('-f', dest='folder', type=str, default='resources',
                    help='Folder where to extract the resources (Default: "./resources"')


if __name__ == '__main__':
    """ Main process in charge of reading the arguments, filling the work queue and creating the workers."""

    # Take arguments
    args = parser.parse_args()
    threads = args.threads
    folder = os.path.join(os.path.abspath("."), args.folder)

    csv = os.path.join(os.path.abspath("."), args.csv)
    if not os.path.isfile(csv):
        print("Wrong input file")
        exit(1)
    else:
        print("Getting work")

    # Initialize job queue
    work_queue = Queue()
    queue_lock = Lock()

    with open(csv, "r") as f:
        for line in f.readlines():
            if len(line.split(",")) > 1:
                continue
            resource = line.replace("\r", "").replace("\n", "")
            work_queue.put(resource)


    # If thread parameter is auto get the (total-1) or the available CPU's, whichever is smaller
    print("Calculating processes...")
    if not threads:
        cpu = cpu_count()
        try:
            available_cpu = len(os.sched_getaffinity(0))
        except Exception as e:
            print("Platform not recognized. Getting the maximum CPU's")
            available_cpu = cpu
        # Save 1 CPU for other purposes
        if cpu > 1 and cpu == available_cpu:
            threads = cpu - 1
        else:
            threads = available_cpu
    print("Processes to run: %d " % threads)

    # Create and call the workers
    print("Spawning new workers...")
    with Pool(processes=threads) as pool:
        p = pool.map(main, [i for i in range(int(threads))])
        pool.close()
        pool.join()