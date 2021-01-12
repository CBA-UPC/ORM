# Basic modules
import argparse
import os
import logging
import logging.config
import queue
import zlib
import json
from multiprocessing import Pool, Queue, cpu_count, Lock

import esprima
from bs4 import BeautifulSoup

# Own modules
import config
from db_manager import Db, Connector
from utils import utc_now, hash_string

logging.config.fileConfig('../logging.conf')

verbose = {"0": logging.CRITICAL, "1": logging.ERROR, "2": logging.WARNING, "3": logging.INFO, "4": logging.DEBUG}

logger = logging.getLogger("MODULE")


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
             "Import": 128}
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


def extract_scripts(code, ast_data):
    """ Extract the embedded scripts and calls the function to compute the codesets. """

    soup = BeautifulSoup(code, 'lxml')
    for script_code in soup.find_all('script', {"src": False}):
        if not extract_ast(script_code.text, ast_data):
            return False
    return True


def extract_ast(code, ast_data):
    """ Computes the codesets for the given code. """

    try:
        ast = esprima.toDict(esprima.parseScript(code, tolerant=True, jsx=True, range=True))
    except Exception as e:
        try:
            code2 = code.decode("utf-8")
            ast = esprima.toDict(esprima.parseScript(code2, tolerant=True, jsx=True, range=True))
        except Exception as e:
            try:
                ast = esprima.toDict(esprima.parseScript(code, tolerant=True, jsx=True, range=True))
            except Exception as e:
                try:
                    code2 = code.decode("utf-8")
                    ast = esprima.toDict(esprima.parseModule(code2, tolerant=True, jsx=True, range=True))
                except Exception as e:
                    return False
    traverse(ast, ast_data)
    return True


def compute_codesets(resource, ast_data):
    """ Inserts the  resource codesets inside the database. """

    for j in range(len(ast_data["subtrees"])):
        #logger.info('Insert codeset %d into database' % j)
        hash_value = hash_string(ast_data["subtrees"][j])
        codeset = Connector(resource.db, "codeset")
        if not codeset.load(hash_value):
            codeset.values.pop('tracking_probability', None)
            codeset.values.pop('dirt_level', None)
            codeset.values["insert_date"] = resource.values["insert_date"]
            codeset.values["update_timestamp"] = resource.values["update_timestamp"]
            codeset.values["tree_nodes"] = int(len(ast_data["subtrees"][j]) / 3)
            if not codeset.save():
                codeset.load(hash_value)
        else:
            codeset.values.pop('tracking_probability', None)
            codeset.values.pop('dirt_level', None)
            if codeset.values["insert_date"] > resource.values["insert_date"]:
                codeset.values["insert_date"] = resource.values["insert_date"]
            if codeset.values["update_timestamp"] < resource.values["update_timestamp"]:
                codeset.values["update_timestamp"] = resource.values["update_timestamp"]
            codeset.save()
        resource.add(codeset, {"offset": ast_data["offset"][j],
                               "length": ast_data["length"][j],
                               "insert_date": resource.values["insert_date"],
                               "update_timestamp": resource.values["update_timestamp"]})
        resource.db.call("ComputeCodesetDirtLevel", values=[codeset.values["id"]])
        resource.db.call("ComputeCodesetPopularityLevel", values=[codeset.values["id"]])


parser = argparse.ArgumentParser(description='JavaScript parser')
parser.add_argument('-t', dest='threads', type=int, default=0,
                    help='Number of threads/processes to span (Default: Auto)')
parser.add_argument('-start', dest='start', type=int, default=0, help='Start index (Default: First)')
parser.add_argument('-end', dest='end', type=int, default=-1, help='End index (Default: Last)', nargs='?')
parser.add_argument('-v', dest='verbose', type=int, default=3,
                    help='Verbose: 0=CRITICAL; 1=ERROR; 2=WARNING; 3=INFO; 4=DEBUG (Default: WARNING)')


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
            logger.info('Job [%d/%d] (proc: %d)' % (total - current + 1, total, process))
            ast_data = {"subtrees": [], "ongoing": [], "offset": [], "length": []}
            resource = Connector(db, "resource")
            resource.load(resource_id)
            rtype = Connector(db, "type")
            rtype.load(resource.values["type"])
            code = zlib.decompress(resource.values["file"])
            failed = False
            if rtype.values["name"] == "Document":
                if not extract_scripts(code, ast_data):
                    if not extract_ast(code, ast_data):
                        failed = True
                        logger.error('Could not compute AST for %s (proc %d)' % (resource.values["hash"], process))
            else:
                if not extract_ast(code, ast_data):
                    if not extract_scripts(code, ast_data):
                        failed = True
                        logger.error('Could not compute AST for %s (proc %d)' % (resource.values["hash"], process))
            if failed:
                continue
            logger.info('%d subtrees (proc: %d)' % (len(ast_data["subtrees"]), process))
            compute_codesets(resource, ast_data)
            resource.values["split"] = 1
            resource.save()
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

    # Get domains between the given range from the database.
    logger.info("Getting work")
    database = Db()
    rq = "SELECT resource.id FROM resource WHERE split = 0"
    if args.start > 0:
        rq += " AND resource.id > %d" % (args.start - 1)
    if args.end > 0:
        rq += " AND resource.id < %d" % (args.end + 1)
    rq += " ORDER BY resource.id"
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
