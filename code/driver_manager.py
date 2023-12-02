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
import logging.config
import zlib

# 3rd party modules
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException
from selenium.common.exceptions import NoSuchWindowException
from selenium.webdriver.common.alert import Alert
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.firefox_profile import FirefoxProfile

# Own modules
from utils import utc_now, extract_domain
from data_manager import manage_requests, parse_internal_links, insert_link
from session_storage import SessionStorage

COMPLETED = REPEAT = True
FAILED = NO_REPEAT = False

logging.config.fileConfig('logging.conf')

logger = logging.getLogger("DRIVER_MANAGER")


def get_extension_uuid(path, identifier):
    uuid = ""
    with open(path + '/prefs.js') as f:
        for line in f.readlines():
            if re.search('extensions.webextensions.uuids', line):
                for elem in line.split(","):
                    if re.search(identifier, elem):
                        uuid = elem.split(":")[1]
    uuid = uuid.replace("\"", "").replace("\\", "").replace("}", "").replace(")", "").replace(";", "")
    return uuid


def build_driver(plugin, cache, update_ublock, process):
    """ Creates the selenium driver to be used by the script and loads the corresponding plugin if needed. """
    try:
        profile = FirefoxProfile()
        # Disable browser content protection measures
        profile.set_preference("dom.storage.default_quota", 51200)
        profile.set_preference("dom.storage.default_site_quota", 51200)
        profile.set_preference("privacy.trackingprotection.enabled", False)
        profile.set_preference("browser.contentblocking.enabled", False)
        profile.set_preference("browser.contentblocking.category", "standard")
        profile.set_preference("browser.contentblocking.database.enabled", False)
        profile.set_preference("browser.contentblocking.fingerprinting.preferences.ui.enabled", False)
        profile.set_preference("browser.contentblocking.cryptomining.preferences.ui.enabled", False)

        # Disable caches and enables private mode for stateless scraps
        if not cache:
            profile.set_preference("browser.cache.disk.enable", False)
            profile.set_preference("browser.cache.memory.enable", False)
            profile.set_preference("browser.cache.offline.enable", False)
            profile.set_preference("network.http.use-cache", False)

        opts = Options()
        opts.profile = profile
        driver = webdriver.Firefox(options=opts, log_path="log/geckodriver.log")
        driver.set_page_load_timeout(15)
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
            if plugin.values['custom'] and update_ublock:
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
        logger.error("(proc. %d) Error creating driver: %s" % (process, str(e)))
        return FAILED


def reset_browser(driver, process, plugin, cache, update_ublock):
    """ Reset the browser to the default state. """

    driver.quit()
    driver = build_driver(plugin, cache, update_ublock, process)
    while not driver:
        driver = build_driver(plugin, cache, update_ublock, process)
    driver.set_page_load_timeout(15)
    return driver


def visit_site(db, process, driver, domain, url, plugin, temp_folder, cache, 
               update_ublock, geo_db, current_deepness, max_deepness, link_dict, parsed_links=0):
    """ Loads the website and extract its information. """

    # Discard already seen URLs
    try:
        blocker_tab_handle = driver.current_window_handle
    except Exception as e:
        logger.error("Error saving uBlock tab: %s (proc. %d)" % (str(e), process))
        driver = reset_browser(driver, process, plugin, cache, update_ublock)
        return driver, FAILED, REPEAT, link_dict, parsed_links
    try:
        driver.execute_script('''window.open();''')
        second_tab_handle = driver.window_handles[-1]
        driver.switch_to.window(second_tab_handle)
    except WebDriverException as e:
        logger.error("WebDriverException (1) on %s / Error: %s (proc. %d)" % (domain.values["name"], str(e), process))
        driver = reset_browser(driver, process, plugin, cache, update_ublock)
        return driver, FAILED, REPEAT, link_dict, parsed_links

    # Load the website and wait some time inside it
    try:
        driver.get(url)
    except TimeoutException:
        logger.warning("Site %s timed out (proc. %d)" % (domain.values["name"], process))
        driver.close()
        driver.switch_to.window(blocker_tab_handle)
        try:
            storage = SessionStorage(driver)
            storage.clear()
        except NoSuchWindowException as e:
            logger.error("(proc. %d) Error accessing the session storage: %s" % (process, str(e)))
            driver = reset_browser(driver, process, plugin, cache, update_ublock)
        except WebDriverException as e:
            logger.error("(proc. %d) Error clearing session storage: %s" % (process, str(e)))
            driver = reset_browser(driver, process, plugin, cache, update_ublock)
        return driver, FAILED, REPEAT, link_dict, parsed_links
    except WebDriverException as e:
        logger.warning("WebDriverException (2) on %s / Error: %s (proc. %d)" % (domain.values["name"], str(e), process))
        driver = reset_browser(driver, process, plugin, cache, update_ublock)
        domain.values["update_timestamp"] = utc_now()
        domain.values["priority"] = 0
        domain.save()
        return driver, FAILED, NO_REPEAT, link_dict, parsed_links
    except Exception as e:
        logger.error("%s (proc. %d)" % (str(e), process))
        driver = reset_browser(driver, process, plugin, cache, update_ublock)
        domain.values["update_timestamp"] = utc_now()
        domain.values["priority"] = 0
        domain.save()
        return driver, FAILED, NO_REPEAT, link_dict, parsed_links

    # Wait some time inside the website
    time.sleep(10)

    # We collect again the URL after redirections
    url = driver.current_url
    
    # Collect website code and screenshot
    os.makedirs(os.path.join(os.path.abspath("."), temp_folder), exist_ok=True)
    filename = os.path.join(temp_folder, domain.values["name"] + 'ss.png')
    driver.save_screenshot(filename)
    webcode = driver.page_source
    size = os.stat(filename).st_size
    compressed_screenshot = None
    if size > 0:
        # Compress the screenshot to save it into the database when needed
        with open(filename, 'rb') as f:
            blob_value = f.read()
            compressed_screenshot = zlib.compress(blob_value)
    os.remove(filename)

    # Close the browser's URL tab
    try:
        # Close possible alerts
        finished = False
        while not finished:
            try:
                alert = Alert(driver)
                alert.dismiss()
            except:
                finished = True
        if not cache:
            driver.delete_all_cookies()
        driver.close()
    except WebDriverException as e:
        logger.warning("WebDriverException (3) on %s / Error: %s (proc. %d)" % (domain.values["name"], str(e), process))
        driver = reset_browser(driver, process, plugin, cache, update_ublock)
        return driver, FAILED, REPEAT, link_dict, parsed_links

    # Process traffic from uBlock Origin tab sessionStorage
    try:
        driver.switch_to.window(blocker_tab_handle)
    except Exception as e:
        logger.error("Error accessing uBlock tab: %s (proc. %d)" % (str(e), process))
        driver = reset_browser(driver, process, plugin, cache, update_ublock)
        return driver, FAILED, REPEAT, link_dict, parsed_links
    try:
        storage = SessionStorage(driver)
        web_list = {}
        for key in storage.keys():
            web_list[key] = storage[key]
    except NoSuchWindowException as e:
        logger.error("(proc. %d) Error accessing the session storage: %s" % (process, str(e)))
        driver = reset_browser(driver, process, plugin, cache, update_ublock)
        return driver, FAILED, REPEAT, link_dict, parsed_links
    else:
        # Insert data and clear storage before opening the next website
        manage_requests(db, process, domain, web_list, current_deepness, plugin, temp_folder, geo_db)
        try:
            storage.clear()
        except WebDriverException as e:
            logger.error("(proc. %d) Error clearing session storage: %s" % (process, str(e)))
            driver = reset_browser(driver, process, plugin, cache, update_ublock)
            return driver, FAILED, NO_REPEAT, link_dict, parsed_links
        
    parsed_links += 1
    if current_deepness < max_deepness:
        # Collect internal links from website's own code
        link_dict = parse_internal_links(db, url, webcode, link_dict)
        total_links = len(link_dict.keys())
        if current_deepness > 0:
            logger.info("(proc. %s): '%s' parsed links [%d/%d]" % (process, domain.values["name"], parsed_links, total_links))

        # Scrape internal links if needed
        for link in link_dict[url]["links_to"]:
            internal_link = link_dict[link]
            # Skip already seen links
            if internal_link["parsed"]:
                continue

            # If it is an external resource from other domain we explore it,
            # but we do not explore any of its internal links
            deepness = current_deepness + 1
            if extract_domain(link) != extract_domain(url):
                deepness = max_deepness
            
            # Scrape the link
            extra_tries = 3
            completed = False
            repeat = True
            logger.info("(proc. %s): Parsing %s" % (process, link))
            while extra_tries > 0 and not completed and repeat:
                extra_tries -= 1
                driver, completed, repeat, link_dict, parsed_links = visit_site(db, process, driver, domain, link, plugin, temp_folder, cache, 
                                                       update_ublock, geo_db, deepness, max_deepness, link_dict, parsed_links)
            if extra_tries > 0:
                insert_link(db, url, link)
    else:
        total_links = len(link_dict.keys())
        if current_deepness > 0:
            logger.info("(proc. %s): '%s' parsed links [%d/%d]" % (process, domain.values["name"], parsed_links, total_links))


    # If this is one of the recursive calls do not save the domain info yet
    if current_deepness != 0:
        return driver, COMPLETED, NO_REPEAT, link_dict, parsed_links
    
    # Save the screenshot and update the db update timestamp
    domain.values["update_timestamp"] = utc_now()
    domain.values["priority"] = 0
    if compressed_screenshot:
        domain.values["screenshot"] = compressed_screenshot
    domain.save()
    return driver, COMPLETED, NO_REPEAT, link_dict, parsed_links
