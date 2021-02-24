# Basic modules
import argparse
import os
import logging.config
import queue
import zlib
import time
import signal
from multiprocessing import Pool, Queue, cpu_count, Lock, Process, Pipe

import esprima
from bs4 import BeautifulSoup
from setproctitle import setproctitle

# Own modules
from db_manager import Db, Connector
from utils import hash_string, utc_now

logging.config.fileConfig('logging.conf')

verbose = {"0": logging.CRITICAL, "1": logging.ERROR, "2": logging.WARNING, "3": logging.INFO, "4": logging.DEBUG}

logger = logging.getLogger("MODULE")


def print_remaining(last_ts, sec, msg):
    now = time.time()
    dif = now - last_ts
    if dif > 1:
        result_queue_lock.acquire()
        result_size = result_queue.qsize()
        result_queue_lock.release()
        sec += int(dif)
        print("", end='\r', flush=True)
        print('[%s] %s %d' % (utc_now(), msg, result_size), end='', flush=True)
        return now, sec
    return last_ts, sec


type_list = {"Program": 998,
             "ClassDeclaration": 996,
             "FunctionDeclaration": 994,
             "MethodDefinition": 992,
             "ClassExpression": 990,
             "FunctionExpression": 988,
             "ArrowFunctionExpression": 986,
             "ArrayPattern": 0,
             "RestElement": 2,
             "AssignmentPattern": 4,
             "ObjectPattern": 6,
             "ThisExpression": 8,
             "Identifier": 10,
             "Literal": 12,
             "ArrayExpression": 14,
             "ObjectExpression": 16,
             "Property": 18,
             "ClassBody": 20,
             "TaggedTemplateExpression": 22,
             "TemplateElement": 24,
             "TemplateLiteral": 26,
             "MemberExpression": 28,
             "Super": 30,
             "MetaProperty": 32,
             "CallExpression": 34,
             "NewExpression": 36,
             "SpreadElement": 38,
             "UpdateExpression": 40,
             "AwaitExpression": 42,
             "UnaryExpression": 44,
             "BinaryExpression": 46,
             "LogicalExpression": 48,
             "ConditionalExpression": 50,
             "YieldExpression": 52,
             "AssignmentExpression": 54,
             "SequenceExpression": 56,
             "BlockStatement": 58,
             "BreakStatement": 60,
             "ContinueStatement": 62,
             "DebuggerStatement": 64,
             "DoWhileStatement": 66,
             "EmptyStatement": 68,
             "ExpressionStatement": 70,
             "ForStatement": 72,
             "ForInStatement": 74,
             "ForOfStatement": 76,
             "IfStatement": 78,
             "LabeledStatement": 80,
             "ReturnStatement": 82,
             "SwitchStatement": 84,
             "SwitchCase": 86,
             "ThrowStatement": 88,
             "TryStatement": 90,
             "CatchClause": 92,
             "VariableDeclaration": 94,
             "VariableDeclarator": 96,
             "WhileStatement": 98,
             "WithStatement": 100,
             "ImportDeclaration": 102,
             "ImportSpecifier": 104,
             "ExportDeclaration": 106,
             "ExportAllDeclaration": 108,
             "ExportDefaultDeclaration": 110,
             "ExportNamedDeclaration": 112,
             "ExportSpecifier": 114,
             "JSXElement": 116,
             "JSXOpeningElement": 118,
             "JSXIdentifier": 120,
             "JSXAttribute": 122,
             "JSXText": 124,
             "JSXClosingElement": 126,
             "JSXExpressionContainer": 127,
             "Import": 128,
             "ImportDefaultSpecifier": 129}
operator_list = {"++": 200,
                 "--": 201,
                 "+": 202,
                 "-": 203,
                 "~": 204,
                 "!": 205,
                 "delete": 206,
                 "void": 207,
                 "typeof": 208,
                 "instanceof": 209,
                 "in": 210,
                 "*": 211,
                 "/": 212,
                 "%": 213,
                 "**": 214,
                 "|": 215,
                 "^": 216,
                 "&": 217,
                 "==": 218,
                 "!=": 219,
                 "===": 220,
                 "!==": 221,
                 "<": 222,
                 ">": 223,
                 "<=": 224,
                 ">=": 225,
                 "=<": 226,
                 "=>": 227,
                 "<<": 228,
                 ">>": 229,
                 ">>>": 230,
                 "||": 231,
                 "&&": 232,
                 "=": 233,
                 "*=": 234,
                 "**=": 235,
                 "/=": 236,
                 "%=": 237,
                 "+=": 238,
                 "-=": 239,
                 "<<=": 240,
                 ">>=": 241,
                 ">>>=": 242,
                 "&=": 243,
                 "^=": 244,
                 "|=": 245}
break_types = ["Program",
               "FunctionDeclaration",
               "MethodDefinition",
               "ClassDeclaration",
               "FunctionExpression",
               "ArrowFunctionExpression",
               "ClassExpression"]
needed_operator = ["LogicalExpression",
                   "UnaryExpression",
                   "BinaryExpression",
                   "AssignmentExpression",
                   "UpdateExpression"]


def start_label(node, ast_data):
    """ Inserts the first label of the node and the operator label if needed in the subtree. """

    if "type" not in node.keys():
        return
    if node["type"] in break_types:
        ast_data["subtrees"].append("%03d" % type_list[node["type"]])
        ast_data["ongoing"].append(True)
        ast_data["offset"].append(int(node["range"][0]))
        ast_data["length"].append(int(node["range"][1]) - ast_data["offset"][-1])
    else:
        for i in range(len(ast_data["ongoing"])):
            if ast_data["ongoing"][i]:
                ast_data["subtrees"][i] += "%03d" % type_list[node["type"]]
                if node["type"] in needed_operator:
                    ast_data["subtrees"][i] += str(operator_list[node["operator"]])


def end_label(node, ast_data):
    """ Inserts the end label for each node on the subtree. """

    if "type" not in node.keys():
        return
    for i in range(len(ast_data["ongoing"])):
        if ast_data["ongoing"][i]:
            ast_data["subtrees"][i] += "%03d" % (type_list[node["type"]] + 1)

    if node["type"] in break_types:
        i = 1
        while not ast_data["ongoing"][len(ast_data["ongoing"]) - i]:
            i += 1
        last = len(ast_data["ongoing"]) - i
        ast_data["ongoing"][last] = False


def traverse(node, ast_data):
    """ Traverses recursively the AST splitting them in subtrees. """

    if not node or "type" not in node.keys():
        return
    start_label(node, ast_data)
    for key in node.keys():
        if isinstance(node[key], list):
            for child in node[key]:
                if isinstance(child, dict):
                    traverse(child, ast_data)
        elif isinstance(node[key], dict):
            traverse(node[key], ast_data)
    end_label(node, ast_data)


def extract_scripts(code, ast_data, worker_number):
    """ Extract the embedded scripts and calls the function to compute the codesets. """

    try:
        soup = BeautifulSoup(code, 'lxml')
        for script_code in soup.find_all('script', {"src": False}):
            if not extract_ast(script_code.text, ast_data, worker_number):
                return False
    except:
        logger.error("AST parsing failed")
        return False
    return True


def extract_ast(code, ast_data, worker_number):
    """ Computes the codesets for the given code. """

    try:
        logger.debug('[Worker %d] Trying leaf 1' % worker_number)
        ast = esprima.toDict(esprima.parseScript(code, tolerant=True, jsx=True, range=True))
    except Exception as e:
        try:
            code2 = code.decode("utf-8")
            logger.debug('[Worker %d] Trying leaf 2' % worker_number)
            ast = esprima.toDict(esprima.parseScript(code2, tolerant=True, jsx=True, range=True))
        except Exception as e:
            try:
                logger.debug('[Worker %d] Trying leaf 3' % worker_number)
                ast = esprima.toDict(esprima.parseScript(code, tolerant=True, jsx=True, range=True))
            except Exception as e:
                try:
                    code2 = code.decode("utf-8")
                    logger.debug('[Worker %d] Trying leaf 4' % worker_number)
                    ast = esprima.toDict(esprima.parseModule(code2, tolerant=True, jsx=True, range=True))
                except Exception as e:
                    logger.error('[Worker %d] Could not create AST' % worker_number)
                    return False
    try:
        traverse(ast, ast_data)
    except:
        logger.error('[Worker %d] Could not parse AST' % worker_number)
        return False
    return True


def compute_codesets(resource, ast_data, worker_number):
    """ Inserts the  resource codesets inside the database. """

    logger.debug("[Worker %d] AST subtrees: %d" % (worker_number, len(ast_data["subtrees"])))
    for j in range(len(ast_data["subtrees"])):
        logger.debug("[Worker %d] Creating subtree %d" % (worker_number, j))
        hash_value = hash_string(ast_data["subtrees"][j])
        logger.debug("[Worker %d] Hash %s" % (worker_number, hash_value))
        codeset = {"hash": hash_value,
                   "tree_nodes": int(len(ast_data["subtrees"][j]) / 3)}
        result_queue_lock.acquire()
        result_queue.put({"codeset": codeset,
                          "resource_id": resource["id"],
                          "offset": ast_data["offset"][j],
                          "length": ast_data["length"][j]})
        result_queue_lock.release()
        logger.debug("[Worker %d] Subtree %d created" % (worker_number, j))


parser = argparse.ArgumentParser(description='JavaScript parser')
parser.add_argument('-t', dest='threads', type=int, default=0,
                    help='Number of threads/processes to span (Default: Auto)')
parser.add_argument('-start', dest='start', type=int, default=0, help='Start index (Default: First)')
parser.add_argument('-end', dest='end', type=int, default=-1, help='End index (Default: Last)', nargs='?')
parser.add_argument('-v', dest='verbose', type=int, default=3,
                    help='Verbose: 0=CRITICAL; 1=ERROR; 2=WARNING; 3=INFO; 4=DEBUG (Default: WARNING)')


def db_work(process_number):
    """ Main process in charge of taking results and save them inside the DB. """

    setproctitle("ORM - Data parser process %d" % process_number)
    finish_signal = False

    # Load the DB manager for this process
    db = Db()

    max_items = 1000
    while not finish_signal:
        if child_pipe.poll():
            child_pipe.recv()
            finish_signal = True
        result_queue_lock.acquire()
        result_size = result_queue.qsize()
        if finish_signal:
            max_items = result_size + 100
        item_list = []
        empty = False
        while len(item_list) < max_items and not empty:
            try:
                item_list.append(result_queue.get(False))
            except queue.Empty:
                empty = True
        result_queue_lock.release()

        resource = Connector(db, "resource")
        for item in item_list:
            # Load the resource if different and mark it as already parsed for codesets
            if "id" not in resource.values.keys() or resource.values["id"] != item["resource_id"]:
                resource.load(item["resource_id"])
                resource.values["split"] = 1
                resource.save()
            setproctitle("ORM - Data parser process %d - Resource %d" % (process_number, resource.values["id"]))

            # Load the codeset and save it if non-existent
            codeset = Connector(db, "codeset")
            if not codeset.load(item["codeset"]["hash"]):
                codeset.values.pop("dirt_level")
                codeset.values.pop("popularity_level")
                codeset.values["tree_nodes"] = item["codeset"]["tree_nodes"]
                codeset.values["resources"] = int(codeset.values["resources"]) + 1
                if resource.values["is_tracking"]:
                    codeset.values["tracking_resources"] = int(codeset.values["tracking_resources"]) + 1
                codeset.save()
            resource.add(codeset, {"offset": item["offset"], "length": item["length"]})
        if empty:
            time.sleep(1)
    db.close()
    child_pipe.send("Finished")
    return


def work(process_number):
    """ Workers process in charge of taking work from the queue and extracting info if needed.

    While there is work in the queue continuously passes new jobs until its empty. """

    setproctitle("ORM - Worker process #%d" % process_number)
    # Load the DB manager for this process

    while True:
        try:
            work_queue_lock.acquire()
            resource_data = work_queue.get(False)
            work_queue_lock.release()
        except queue.Empty:
            work_queue_lock.release()
            time.sleep(1)
        except Exception as e:
            logger.error("[Worker %d] %s" % (process_number, str(e)))
        else:
            setproctitle("ORM - Worker process #%d - Resource %d" % (process_number, resource_data["id"]))
            logger.debug('[Worker %d] Resource %s' % (process_number, resource_data["id"]))
            ast_data = {"subtrees": [], "ongoing": [], "offset": [], "length": []}
            code = zlib.decompress(resource_data["file"])
            if resource_data["type"] == "frame":
                if not extract_scripts(code, ast_data, process_number):
                    if not extract_ast(code, ast_data, process_number):
                        logger.error('[Worker %d] Could not compute AST for %d' % (process_number, resource_data["id"]))
                        return
            elif resource_data["type"] == "script":
                if not extract_ast(code, ast_data, process_number):
                    if not extract_scripts(code, ast_data, process_number):
                        logger.error('[Worker %d] Could not compute AST for %d' % (process_number, resource_data["id"]))
                        return
            compute_codesets(resource_data, ast_data, process_number)


if __name__ == '__main__':
    """ Main process in charge of reading the arguments, filling the work queue and creating the workers."""

    setproctitle("ORM - Main process")
    sc = 0
    ts = time.time()
    # Inhibit signals on work creation
    original_sigint_handler = signal.signal(signal.SIGINT, signal.SIG_IGN)

    # Take arguments
    args = parser.parse_args()
    threads = args.threads
    v = args.verbose
    if verbose[str(v)]:
        logger.setLevel(verbose[str(v)])

    # If thread parameter is auto get the (total-1) or the available CPU's, whichever is smaller
    logger.info("[Main process] Calculating workers...")
    if not threads:
        cpu = cpu_count()
        try:
            available_cpu = len(os.sched_getaffinity(0))
        except Exception as e:
            logger.warning("[Main process] Platform not recognized. Getting the maximum CPU's")
            available_cpu = cpu
        if cpu > 1 and cpu == available_cpu:
            threads = cpu - 1
        else:
            threads = available_cpu
    logger.info("[Main process] Workers to run: %d " % threads)

    work_queue = Queue()
    result_queue = Queue()
    work_queue_lock = Lock()
    result_queue_lock = Lock()
    parent_pipe, child_pipe = Pipe()
    last_resource_id = -1

    # Create and call the workers
    logger.debug("[Main process] Spawning new workers...")
    with Pool(processes=int(threads/2)) as pool, Pool(processes=int(threads/2)) as data_pool:
        dp = data_pool.map_async(db_work, [i for i in range(int(threads/2))])
        p = pool.map_async(work, [i for i in range(int(threads/2))])

        # Restore signal on main thread
        signal.signal(signal.SIGINT, original_sigint_handler)

        try:
            while True:
                ts, sc = print_remaining(ts, sc, "Codeset queue size:")
                # Insert new work into queue if needed.
                work_queue_lock.acquire()
                qsize = work_queue.qsize()
                work_queue_lock.release()
                if qsize < (2 * threads):
                    logger.debug("[Main process] Getting work")
                    database = Db()
                    rq = 'SELECT id, type, file FROM resource WHERE split = 0 AND size > 0 '
                    rq += ' AND type IN ("frame", "script")'
                    rq += ' AND id > %d' % last_resource_id
                    rq += ' ORDER BY id LIMIT 200'
                    results = database.custom(rq)
                    database.close()
                    # If no new work wait ten seconds and retry
                    if len(results) > 0:
                        # Initialize job queue
                        last_resource_id = results[-1]["id"]
                        logger.debug("[Main process] Enqueuing work")
                        work_queue_lock.acquire()
                        for result in results:
                            work_queue.put({"id": result["id"], "type": result["type"], "file": result["file"]})
                        work_queue_lock.release()
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("[Main process] Keyboard interrupt received. Clearing work queue...")
            remaining = True
            work_queue_lock.acquire()
            while remaining:
                try:
                    garbage = work_queue.get(False)
                except queue.Empty:
                    remaining = False
            work_queue_lock.release()

            # Tell the db worker to finish when possible
            logger.info("[Main process] Waiting for DB worker to save collected info...")
            parent_pipe.send("Finish")

            # Wait for the db workers to finish
            for i in range(int(threads/3)):
                parent_pipe.recv()

            logger.info("[Main process] Work finished. Bye bye!")
            exit(0)
