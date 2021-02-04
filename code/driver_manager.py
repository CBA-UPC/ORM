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

# Basic modules
import os
import re
import time
import logging
import logging.config

# 3rd party modules
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException
from selenium.common.exceptions import NoSuchWindowException

# Own modules
import config
from data_manager import manage_requests
from session_storage import SessionStorage

COMPLETED = REPEAT = True
FAILED = NO_REPEAT = False

logging.config.fileConfig('../logging.conf')

logger = logging.getLogger("DRIVER_MANAGER")


def get_extension_uuid(path, identifier):
    uuid = ""
    with open(path + '/prefs.js') as f:
        for line in f.readlines():
            if re.search('extensions.webextensions.uuids', line):
                for elem in line.split(","):
                    if re.search(identifier, elem):
                        uuid = elem.split(":")[1]
    uuid = uuid.replace("\"", "").replace("\\", "").replace("}", "").replace(")", "").replace(";","")
    return uuid


def build_driver(plugin, cache, process):
    """ Creates the selenium driver to be used by the script and loads the corresponding plugin if needed. """
    try:
        profile = webdriver.FirefoxProfile()
        # Disable browser content protection measures
        profile.set_preference("privacy.trackingprotection.enabled", False)
        profile.set_preference("browser.contentblocking.enabled", False)

        # Disable caches and enables private mode for stateless scraps
        if not cache:
            profile.set_preference("browser.cache.disk.enable", False)
            profile.set_preference("browser.cache.memory.enable", False)
            profile.set_preference("browser.cache.offline.enable", False)
            profile.set_preference("network.http.use-cache", False)

        driver = webdriver.Firefox(profile)
        driver.set_page_load_timeout(60)
    except Exception as e:
        # logger.error(e)
        logger.error("(proc. %d) Error creating driver: %s" % (process, str(e)))
        return FAILED
    try:
        time.sleep(2)
        # Load received plugin (except for vanilla)
        if plugin.values["name"] != "Vanilla":
            plugin_path = os.path.join(os.path.abspath("."), plugin.values["path"])
            driver.install_addon(plugin_path, temporary=True)
            time.sleep(2)
            profile_path = str(driver.capabilities['moz:profile'])
            uuid = get_extension_uuid(profile_path, plugin.values["identifier"])
            if plugin.values['custom']:
                driver.get(plugin.values['url'].replace("UUID", uuid))
                time.sleep(10)
                try:
                    driver.find_element_by_xpath(plugin.values['xpath_to_click']).click()
                except NoSuchElementException as e:
                    driver.switch_to.frame(0)
                    driver.find_element_by_xpath(plugin.values['xpath_to_click']).click()
                time.sleep(20)
            if plugin.values["background"]:
                driver.get(plugin.values["background"].replace("UUID", uuid))
        return driver
    except Exception as e:
        driver.quit()
        # logger.error(e)
        logger.error("(proc. %d) Error creating driver: %s" % (process, str(e)))
        return FAILED


def reset_browser(driver, process, plugin, cache):
    """ Reset the browser to the default state. """

    driver.quit()
    driver = build_driver(plugin, cache, process)
    while not driver:
        driver = build_driver(plugin, cache, process)
    driver.set_page_load_timeout(60)
    return driver


def visit_site(db, process, driver, domain, plugin, temp_folder, cache, geo_db):
    """ Loads the website and extract its information. """

    blocker_tab_handle = driver.current_window_handle
    try:
        driver.execute_script('''window.open();''')
        second_tab_handle = driver.window_handles[-1]
        driver.switch_to.window(second_tab_handle)
    except WebDriverException as e:
        logger.warning("WebDriverException (1) on %s / Error: %s (proc. %d)" % (domain.values["name"], str(e), process))
        driver = reset_browser(driver, process, plugin, cache)
        return driver, FAILED, REPEAT

    # Load the website and wait some time inside it
    try:
        driver.get('http://' + domain.values["name"])
    except TimeoutException:
        logger.warning("Site %s timed out (proc. %d)" % (domain.values["name"], process))
        driver.close()
        driver.switch_to.window(blocker_tab_handle)
        try:
            storage = SessionStorage(driver)
            storage.clear()
        except NoSuchWindowException as e:
            logger.error("(proc. %d) Error accessing the session storage: %s" % (process, str(e)))
            driver = reset_browser(driver, process, plugin, cache)
        except WebDriverException as e:
            logger.error("(proc. %d) Error clearing session storage: %s" % (process, str(e)))
            driver = reset_browser(driver, process, plugin, cache)
        return driver, FAILED, NO_REPEAT
    except WebDriverException as e:
        logger.warning("WebDriverException (2) on %s / Error: %s (proc. %d)" % (domain.values["name"], str(e), process))
        driver = reset_browser(driver, process, plugin, cache)
        return driver, FAILED, NO_REPEAT
    except Exception as e:
        logger.error("%s (proc. %d)" % (str(e), process))
        driver = reset_browser(driver, process, plugin, cache)
        return driver, FAILED, NO_REPEAT
    time.sleep(10)
    try:
        if not cache:
            driver.delete_all_cookies()
        driver.close()
    except WebDriverException as e:
        logger.warning("WebDriverException (3) on %s / Error: %s (proc. %d)" % (domain.values["name"], str(e), process))
        driver = reset_browser(driver, process, plugin, cache)
        return driver, FAILED, REPEAT

    # Process traffic from uBlock Origin tab sessionStorage
    driver.switch_to.window(blocker_tab_handle)
    try:
        storage = SessionStorage(driver)
        web_list = {}
        for key in storage.keys():
            web_list[key] = storage[key]
    except NoSuchWindowException as e:
        logger.error("(proc. %d) Error accessing the session storage: %s" % (process, str(e)))
        driver = reset_browser(driver, process, plugin, cache)
        return driver, FAILED, REPEAT
    else:
        # Insert data and clear storage before opening the next website
        manage_requests(db, process, domain, web_list, plugin, temp_folder, geo_db)
        try:
            storage.clear()
        except WebDriverException as e:
            logger.error("(proc. %d) Error clearing session storage: %s" % (process, str(e)))
            driver = reset_browser(driver, process, plugin, cache)
            return driver, FAILED, NO_REPEAT
    return driver, COMPLETED, NO_REPEAT
