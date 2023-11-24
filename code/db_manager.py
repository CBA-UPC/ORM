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


""" This module defines a generic way to communicate with the MySQL database.

This module takes advantage of the regular database structure to ease the
requests and data management.

It basically has two different classes: db and Connector.
- db: defines some standard methods to create the most basic query structures
for accessing database tables.
- Connector: uses db class to represent a database table inside the
application.

To search for an item in the database you have to create a Connector passing
as a parameter a string with the table you want to load data from, then call
the method 'load' passing as a parameter the id as an integer or the 'hash' as
a string to look for, and the Connector creates the request and searches the
item in the database.

Once you have the item you can just get the related data calling the 'get'
function with the table you want to take the data from. The 'get' function
looks for the related data using the previously gotten element id and it
returns a list of Connectors containing the data. You can then look for other
related data using the returned Connectors.

Inside each connector there is a parameter called 'values' that contains a list
with all the selected table column information (the selected element properties).
You can then modify those values and call the method 'save' to update the
values in the database table.

When you want to create a new row in a table you only need to create a new
Connector to that table, call the 'load' method with the new hash you want
to insert in the table, and if the element doesn't already exist the method
will return a new Connector element with all the columns of the table
initialized as None values. You only have to insert the values in the
list, and when you call the 'save' method it will insert the row into the
table as a new row.

There is an extra function called 'get_all' that returns all the elements
inside the table of the Connector. If for example you want to take all the
domains, you call a new Connector passing 'domain' as the table name,
and then call the 'get_all' function to get all the domains. The results are
returned as a list of Connectors representing the given data.

This way of management simplifies a lot the database requests needed inside the
code but clearly over-generates requests. For the sake of speed and performance
there are some other specific requests included in the Connector to get some
extensive data that will slow the loading a lot using only the simple methods.

Last, there is a function called 'custom' where you can generate a custom
request for specific reasons.

"""

# Basic modules
import MySQLdb
import re
import logging.config

import config
from utils import hash_string

logging.config.fileConfig('logging.conf')
logger = logging.getLogger("DB_MANAGER")

CROSS_TABLES = ["domain_url", "resource_fingerprint", "resource_codeset", "resource_tracking", "url_tracking"]


class Db(object):
    """
    This class manages the basic database operations. It defines the most
    basic requests taking into account the database table definitions to
    make easier the data management.
    """

    def __init__(self,
                 host=config.MYSQL_HOST,
                 port=config.MYSQL_PORT,
                 user=config.MYSQL_USER,
                 password=config.MYSQL_PASSWORD,
                 db=config.MYSQL_DB):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.db = db
        self.conn = MySQLdb.connect(host=self.host, port=self.port, user=self.user, passwd=self.password, db=self.db,
                                    use_unicode=True, charset='utf8mb4')

    def close(self):
        """ Closes the connection to the database. """

        self.conn.close()

    def initialize(self, sites, timestamp):
        """ initializes the database with the Tranco's list domain information. """

        for domain in sites.keys():
            # domain = extract_domain(domain)
            print(str(sites[domain]["tranco_rank"]) + ": " + sites[domain]["name"])
            hash_key = hash_string(domain)
            element = {"hash": hash_key, "name": domain, "tranco_rank": sites[domain]["tranco_rank"],
                       "insert_date": timestamp}
            element_id = self.custom(query="SELECT id FROM domain WHERE domain.hash = %s", values=[hash_key])
            if not element_id:
                self.insert("domain", element)
            else:
                element["id"] = element_id[0]["id"]
                self.update("domain", element)

    def __select(self, fields, tables, conditions, order, values, log=None):
        """ Creates a standard SELECT request. """

        request = "SELECT "
        field_list = ", ".join(fields)
        request += field_list
        request += " FROM " + ", ".join(tables)
        if conditions:
            cond_list = " WHERE "
            for index, cond in enumerate(conditions):
                cond_list += "(" + cond
                if values[index] == "NULL":
                    cond_list += " IS %s)"
                    values[index] = None
                elif values[index] == "NOT NULL":
                    cond_list += " IS NOT %s)"
                    values[index] = None
                else:
                    cond_list += " = %s)"
                if index < len(conditions) - 1:
                    cond_list += " AND "
            request += cond_list
        if order:
            #            request += " ORDER BY '"+"', '".join(order)+"'"
            request += " ORDER BY " + ", ".join(order)
        self.conn.ping()
        cursor = self.conn.cursor(MySQLdb.cursors.DictCursor)
        results = []
        try:
            if values:
                if log:
                    logger.debug(request % tuple(values))
                cursor.execute(request, tuple(values))
            else:
                if log:
                    logger.debug(request)
                cursor.execute(request)
        except MySQLdb.Error as error:
            if values:
                logger.error(request % tuple(values))
            else:
                logger.error(request)
            logger.error("SQL ERROR: " + str(error) + "\n-----------------")
        else:
            for row in cursor.fetchall():
                result = {}
                for key in row.keys():
                    result[key] = row[key]
                    if row[key] == "NULL":
                        result[key] = None
                results.append(result)
            if log:
                logger.debug("REQUEST OK. Results: " + str(results) + "\n-----------------")
        cursor.close()
        return results

    def __insert(self, table, fields, values, log=None):
        """ Creates a standard INSERT request. """

        if fields and len(fields) != len(values):
            logger.warning("Incorrect number of field/values")
            return 0
        request = "INSERT INTO " + table
        if fields:
            request += " (" + fields[0]
            if len(fields) > 1:
                for index in range(1, len(fields)):
                    request += ", " + fields[index]
            request += ")"
        request += " VALUES (%s"
        if len(values) > 1:
            for index in range(1, len(values)):
                request += ", %s"
        request += ")"
        request += " ON DUPLICATE KEY UPDATE "
        if fields:
            request += fields[0]+"=%s"
            if len(fields) > 1:
                for index in range(1, len(fields)):
                    request += ", " + fields[index] + "=%s"
        new_values = values.copy()
        for value in new_values:
            values.append(value)
        self.conn.ping()
        cursor = self.conn.cursor(MySQLdb.cursors.DictCursor)
        try:
            if log:
                logger.debug(request % tuple(values))
            cursor.execute(request, tuple(values))
        except MySQLdb.Error as error:
            logger.error(request % tuple(values))
            logger.error("SQL ERROR: " + str(error) + "\n-----------------")
            return 0
        else:
            self.conn.commit()
            if log:
                logger.debug("REQUEST OK. Id: " + str(cursor.lastrowid) + "\n-----------------")
            last_row_id = cursor.lastrowid
            cursor.close()
            return last_row_id

    def __update(self, table, fields, conditions, values, log=None):
        """ Creates a standard UPDATE request. """

        if fields and len(fields) + len(conditions) != len(values):
            logger.warning("Incorrect number of fields/conditions/values")
            return 0
        request = "UPDATE IGNORE " + table
        request += " SET " + fields[0] + " = %s"
        if len(fields) > 1:
            for index in range(1, len(fields)):
                request += ", " + fields[index] + " = %s"
        request += " WHERE " + conditions[0] + " = %s"
        if len(conditions) > 1:
            for index in range(1, len(conditions)):
                request += " AND " + conditions[index] + " = %s"
        self.conn.ping()
        cursor = self.conn.cursor(MySQLdb.cursors.DictCursor)
        try:
            if log:
                logger.debug(request % tuple(values))
            cursor.execute(request, tuple(values))
        except MySQLdb.Error as error:
            deadlock = 0
            if re.search('Deadlock', str(error)):
                deadlock = 1
            while deadlock:
                try:
                    cursor.execute(request % tuple(values))
                except MySQLdb.Error as e:
                    if not re.search('Deadlock', str(e)):
                        deadlock = 0
                        error = e
                else:
                    self.conn.commit()
                    if log:
                        logger.debug("REQUEST OK.\n-----------------")
                    cursor.close()
                    return -1
            logger.error(request % tuple(values))
            logger.error("SQL ERROR: " + str(error) + "\n-----------------")
            cursor.close()
            return 0
        else:
            self.conn.commit()
            if log:
                logger.debug("REQUEST OK.\n-----------------")
            cursor.close()
            return -1

    def _delete(self, table, conditions, values, log=None):
        """ Creates a standard DELETE request. """

        request = "DELETE FROM " + table
        request += " WHERE " + conditions[0] + " = %s"
        if len(conditions) > 1:
            for index in range(1, len(conditions)):
                request += " AND " + conditions[index] + " = %s"
        self.conn.ping()
        cursor = self.conn.cursor(MySQLdb.cursors.DictCursor)
        try:
            if log:
                logger.debug(request % tuple(values))
            cursor.execute(request, tuple(values))
        except MySQLdb.Error as error:
            logger.error(request % tuple(values))
            logger.error("SQL ERROR: " + str(error) + "\n-----------------")
            cursor.close()
            return 0
        else:
            self.conn.commit()
            if log:
                logger.debug("REQUEST OK.\n-----------------")
                cursor.close()
            return 1

    def custom(self, query, values=None, log=None):
        """ Creates a custom request. """

        if values is None:
            values = []
        request = query
        self.conn.ping()
        cursor = self.conn.cursor(MySQLdb.cursors.DictCursor)
        results = []
        try:
            if values:
                if log:
                    logger.debug(request % tuple(values))
                cursor.execute(request, tuple(values))
            else:
                if log:
                    logger.debug(request)
                cursor.execute(request)
        except MySQLdb.Error as error:
            logger.error("SQL ERROR: " + str(error) + "\n-----------------")
        else:
            if re.match("DELETE", request) is not None:
                self.conn.commit()
            elif re.match("INSERT", request) is not None:
                self.conn.commit()
            elif re.match("UPDATE", request) is not None:
                self.conn.commit()
            for row in cursor.fetchall():
                result = {}
                for key in row.keys():
                    result[key] = row[key]
                results.append(result)
            if log:
                logger.debug("REQUEST OK. Results: " + str(results) + "\n-----------------")
        cursor.close()
        return results

    def call(self, name, values=None, log=None):
        """ Calls a stored procedure. """

        if values is None:
            values = []
        self.conn.ping()
        cursor = self.conn.cursor(MySQLdb.cursors.DictCursor)
        results = []
        try:
            if values:
                if log:
                    logger.debug("PROCEDURE CALL: " + name + "| PARAMETERS: " + str(tuple(values)))
                cursor.callproc(name, tuple(values))
            else:
                if log:
                    logger.debug("PROCEDURE CALL: " + name)
                cursor.callproc(name)
        except MySQLdb.Error as error:
            logger.error("SQL ERROR: " + str(error) + "\n-----------------")
        else:
            #self.conn.commit()
            for row in cursor.fetchall():
                result = {}
                for key in row.keys():
                    result[key] = row[key]
                results.append(result)
            if log:
                logger.debug("REQUEST OK. Results: " + str(results) + "\n-----------------")
        cursor.close()
        return results

    def select(self, fields, tables, conditions, order, values, log=None):
        """ Calls the internal __select function. """

        result = self.__select(fields, tables, conditions, order, values, log)
        return result

    def insert(self, table, element, log=None):
        """ Insert the element if it can be updated first (doesn't exists). """

        update = self.update(table, element, log)
        if update:
            return update
        fields = []
        values = []
        for key in element.keys():
            fields.append(key)
            values.append(element[key])
        result = self.__insert(table, fields, values, log)
        return result

    def update(self, table, element, log=None):
        """ Update the table for the given element id. """

        if "id" not in element.keys():
            return 0
        fields = []
        conditions = []
        values = []
        for key in element.keys():
            if key != "id":
                fields.append(key)
                values.append(element[key])
        conditions.append("id")
        values.append(element["id"])
        result = self.__update(table, fields, conditions, values, log)
        if result == -1:
            return element["id"]
        return result

    def delete(self, table, element, log=None):
        """ Removes the element from the table. """

        conditions = ["id"]
        values = element["id"]
        result = self._delete(table, conditions, [values], log)
        return result


class Connector(object):
    """
    This class defines the basic objects used for accessing the database
    (one object per table), and the getters and setters for them.
    This makes the data management a lot easier at the cost of an increased
    number of database requests.
    """

    def __init__(self, db, table, order=None, log=False):
        self.table = table
        self.log = log
        self.db = db
        self.db.conn.ping()
        if order:
            self.order = [order]
        else:
            self.order = []
        self.values = {}

    def __str__(self):
        return str(self.values)

    def __eq__(self, other):
        if not isinstance(other, Connector):
            # don't attempt to compare against unrelated types
            return NotImplemented

        if len(self.values) != len(other.values):
            return False

        for key in self.values:
            if key not in other.values:
                return False
            if self.values[key] != other.values[key]:
                return False

        return True

    def load(self, value, args=None):
        """ Loads the element depending on the given value. """

        if args is None:
            args = {}
        conditions = ["id"]
        values = [value]
        if isinstance(value, str):
            conditions = ["hash"]
            self.values[conditions[0]] = value
        for key in args.keys():
            conditions.append(key)
            values.append(args[key])
        result = self.db.select("*", [self.table], conditions, self.order, values, self.log)
        if not result:
            pragma = self.db.custom("desc %s" % self.table)
            for i in pragma:
                if not i["Default"]:
                    self.values[i["Field"]] = None
                else:
                    self.values[i["Field"]] = i["Default"]
            self.values[conditions[0]] = value
            return 0
        if len(result) > 1:
            logger.warning("Loading " + self.table + " '" + str(value) + "': Too many query results")
            return 0
        self.values = result[0]
        return self.values["id"]

    def save(self):
        """ Saves the element values in the corresponding table. """

        #        nulls = []
        if "id" in self.values.keys() and not self.values["id"]:
            del self.values["id"]
        response = self.db.insert(self.table, self.values, self.log)
        if not response:
            return 0
        self.load(response)
        return 1

    def delete(self):
        """ Deletes the element inside the Connector. """

        response = self.db.delete(self.table, self.values, self.log)
        if not response:
            return 0
        #        self.values = {}
        return response

    def get(self, etype, order="id", args=None):
        """ Get the relatives of the given type.

        If args is not empty it will get only the elements that comply with
        the conditions specified as the dict keys and the values inside each
        condition. """
        if args is None:
            args = {}
        if etype + "_id" in self.values.keys():
            if not self.values[etype + "_id"]:
                return None
            element = type(self)
            element = element(self.db, etype)
            element.load(self.values[etype + "_id"])
            return element
        requests = []
        tables = []
        conditions = [self.table + "_id"]
        orders = [order]
        values = [self.values["id"]]
        for key in args.keys():
            conditions.append(key)
            values.append(args[key])
        if self.table + "_" + etype in CROSS_TABLES:
            requests.append("DISTINCT " + etype + "_id")
            tables.append(self.table + "_" + etype)
        elif etype + "_" + self.table in CROSS_TABLES:
            requests.append("DISTINCT " + etype + "_id")
            tables.append(etype + "_" + self.table)
        else:
            requests.append("DISTINCT id")
            tables.append(etype)
        ids = self.db.select(requests, tables, conditions, orders, values, self.log)
        elements = []
        for index in ids:
            element = type(self)
            element = element(self.db, etype)
            element.load(index[requests[0].replace("DISTINCT ", "")])
            elements.append(element)
        return elements

    def add(self, element, args=None):
        """ Add a new relation with the given element.

        This function is only used to create relations where exists
        specific relation tables in the form element1_id, element2_id. """
        if args is None:
            args = {}
        requests = ["DISTINCT id"]
        tables = []
        conditions = [self.table + "_id", element.table + "_id"]
        orders = ["id"]
        values = [self.values["id"], element.values["id"]]
        if self.table + "_" + element.table in CROSS_TABLES:
            tables.append(self.table + "_" + element.table)
        elif element.table + "_" + self.table in CROSS_TABLES:
            tables.append(element.table + "_" + self.table)
        else:
            return 0
        ids = self.db.select(requests, tables, conditions, orders, values, self.log)
        new_element = type(self)
        new_element = new_element(self.db, tables[0])
        if not ids:
            new_element.values[self.table + "_id"] = self.values["id"]
            new_element.values[element.table + "_id"] = element.values["id"]
        else:
            new_element.load(ids[0]["id"])
        for key in args.keys():
            if key == "insert_date" and "insert_date" in new_element.values.keys() and \
                    new_element.values["insert_date"]:
                continue
            new_element.values[key] = args[key]
        if not new_element.save():
            new_element.load(ids[0]["id"])
        return new_element

    def add_double(self, element1, element2, args=None):
        """ Add a new relation with the given element.

        This function is only used to create relations where exists
        specific relation tables in the form element1_id, element2_id. """
        if args is None:
            args = {}
        requests = ["DISTINCT id"]
        tables = []
        conditions = [self.table + "_id", element1.table + "_id", element2.table + "_id"]
        orders = ["id"]
        values = [self.values["id"], element1.values["id"], element2.values["id"]]
        if "resource_id" in args.keys():
            values.append(args["resource_id"])
        if self.table + "_" + element1.table in CROSS_TABLES:
            tables.append(self.table + "_" + element1.table)
        elif element1.table + "_" + self.table in CROSS_TABLES:
            tables.append(element1.table + "_" + self.table)
        elif self.table + "_" + element2.table in CROSS_TABLES:
            tables.append(self.table + "_" + element2.table)
        elif element2.table + "_" + self.table in CROSS_TABLES:
            tables.append(element2.table + "_" + self.table)
        else:
            return 0
        ids = self.db.select(requests, tables, conditions, orders, values, self.log)
        new_element = type(self)
        new_element = new_element(self.db, tables[0])
        if not ids:
            new_element.values[self.table + "_id"] = self.values["id"]
            new_element.values[element1.table + "_id"] = element1.values["id"]
            new_element.values[element2.table + "_id"] = element2.values["id"]
        else:
            new_element.load(ids[0]["id"])
        for key in args.keys():
            if key == "insert_date" and "insert_date" in new_element.values.keys() and \
                    new_element.values["insert_date"]:
                continue
            new_element.values[key] = args[key]
        if not new_element.save():
            new_element.load(ids[0]["id"])
        return new_element

    def remove(self, element):
        """ Removes the relation between two different items. """

        requests = ["id"]
        tables = []
        conditions = [self.table + "_id", element.table + "_id"]
        orders = ["id"]
        values = [self.values["id"], element.values["id"]]
        if self.table + "_" + element.table in CROSS_TABLES:
            tables.append(self.table + "_" + element.table)
        elif element.table + "_" + self.table in CROSS_TABLES:
            tables.append(element.table + "_" + self.table)
        else:
            return 0
        ids = self.db.select(requests, tables, conditions, orders, values, self.log)
        if not ids:
            return 1
        values = {"id": ids[0]["id"]}
        return Db().delete(tables[0], values)

    def clean(self, etype, args=None):
        """ Removes all the elements of the given type that relates to the Connector. """

        if args is None:
            args = {}
        conditions = [self.table + "_id"]
        values = [self.values["id"]]
        for key in args.keys():
            conditions.append(key)
            values.append(args[key])
        if self.table + "_" + etype in CROSS_TABLES:
            tables = self.table + "_" + etype
        elif etype + "_" + self.table in CROSS_TABLES:
            tables = etype + "_" + self.table
        else:
            tables = etype
        result = self.db._delete(tables, conditions, values, self.log)
        return result

    def get_all(self, args=None):
        """ Gets ALL the table items in a collection of Connectors.

        If args is not empty it will only get the elements that comply with
        the passed conditions as the 'get' function. """
        if args is None:
            args = {}
        requests = ["*"]
        tables = [self.table]
        conditions = []
        orders = self.order
        values = []
        for key in args.keys():
            conditions.append(key)
            values.append(args[key])
        ids = self.db.select(requests, tables, conditions, orders, values, self.log)
        elements = []
        for index in ids:
            element = type(self)
            element = element(self.db, self.table)
            element.order = self.order
            element.values = index
            elements.append(element)
        return elements

    def get_property(self, prop="hash", args=None):
        """ Gets ALL keys in a collection of Connectors.

        If args is not empty it will only get the elements that comply with
        the passed conditions as the 'get' function. """
        if args is None:
            args = {}
        requests = ["DISTINCT " + prop]
        tables = [self.table]
        conditions = []
        orders = self.order
        values = []
        for key in args.keys():
            conditions.append(key)
            values.append(args[key])
        keys = []
        results = self.db.select(requests, tables, conditions, orders, values, self.log)
        for result in results:
            keys.append(result[prop])
        return keys

    def count(self, args=None):
        """ Counts the elements of the Connector table.

        If args is not empty it will only count the elements that comply with
        the passed conditions as the 'get' function. """
        if args is None:
            args = {}
        conditions = []
        values = []
        for key in args.keys():
            conditions.append(key)
            values.append(args[key])
        request = "SELECT COUNT (id) FROM " + self.table
        if conditions:
            request = request + " WHERE "
        for index, cond in enumerate(conditions):
            if values[index] == "NULL":
                request += cond + " IS %s"
                values[index] = None
            elif values[index] == "NOT NULL":
                request += cond + " IS NOT %s"
                values[index] = None
            else:
                request += cond + " = %s"
            if index < len(conditions) - 1:
                request += " AND "
        result = self.db.custom(request, values, self.log)
        return result[0]["COUNT (id)"]

