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


"""
* Class to easily manipulate the driver sessionStorage.
* It is mainly used by the driver_manager.py to access the
* blocked resource information from the custom uBlock Origin
* extension storage.
"""


class SessionStorage:

    def __init__(self, driver):
        self.driver = driver

    def __len__(self):
        return self.driver.execute_script("return window.sessionStorage.length;")

    def items(self):
        return self.driver.execute_script("var ls = window.sessionStorage, items = {}; "
                                          "for (var i = 0, k; i < ls.length; ++i) "
                                          "  items[k = ls.key(i)] = ls.getItem(k); "
                                          "return items; ")

    def keys(self):
        return self.driver.execute_script("var ls = window.sessionStorage, keys = []; "
                                          "for (var i = 0; i < ls.length; ++i) "
                                          "keys[i] = ls.key(i); "
                                          "return keys; ")

    def get(self, key):
        return self.driver.execute_script("return window.sessionStorage.getItem(arguments[0]);", key)

    def set(self, key, value):
        self.driver.execute_script("window.sessionStorage.setItem(arguments[0], arguments[1]);", key, value)

    def has(self, key):
        return key in self.keys()

    def remove(self, key):
        self.driver.execute_script("window.sessionStorage.removeItem(arguments[0]);", key)

    def clear(self):
        self.driver.execute_script("window.sessionStorage.clear();")

    def __getitem__(self, key):
        value = self.get(key)
        if value is None:
            raise KeyError(key)
        return value

    def __setitem__(self, key, value):
        self.set(key, value)

    def __contains__(self, key):
        return key in self.keys()

    def __iter__(self):
        return self.items().__iter__()

    def __repr__(self):
        return self.items().__str__()
