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
from pyshadow.main import Shadow
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException
from selenium.common.exceptions import NoSuchWindowException, InvalidArgumentException, ElementNotInteractableException, ElementClickInterceptedException, StaleElementReferenceException, NoSuchElementException
from selenium.webdriver.common.alert import Alert
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.firefox_profile import FirefoxProfile
from selenium.webdriver.firefox.service import Service # Used to define geckodriver bin + log_path in selenium 4.16

# Own modules
from utils import utc_now, extract_domain
from db_manager import Db, Connector
from data_manager import manage_requests, parse_internal_links, insert_link
from session_storage import SessionStorage


# Paths to be used in production server
geckodriver_path = os.path.join(os.path.abspath("."), "../assets/firefox/geckodriver-v0.33.0-linux64/geckodriver")
firefox_path     = os.path.join(os.path.abspath("."), "../assets/firefox/firefox-115.5.0esr/firefox/firefox")

# Hardcoded paths for the virtual machine
# geckodriver_path = "/home/eprivo/Desktop/geckodriver-v0.33.0-linux64/geckodriver"
# firefox_path     = "/home/eprivo/Desktop/firefox-115.5.0esr/firefox/firefox"


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


def build_driver(cache, update_ublock, process):
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
        opts.binary_location = firefox_path
        
        geckodriver_service = Service(executable_path=geckodriver_path,
                                      log_path="log/geckodriver.log")
        
        driver = webdriver.Firefox(service=geckodriver_service,
                                   options=opts)
        
        driver.set_page_load_timeout(15)
    except Exception as e:
        # logger.error(e)
        logger.error("[Worker %d] Error creating driver: %s" % (process, str(e)))
        return FAILED
    try:
        time.sleep(2)

        # Load enabled plugins
        db = Db()
        plugin_list = Connector(db, "plugin")
        plugin_list = plugin_list.get_all({"enabled": 1})

        # Load received plugin (except for vanilla)
        for plugin in plugin_list:
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
        logger.error("[Worker %d] Error creating driver: %s" % (process, str(e)))
        return FAILED


def reset_browser(driver, process, cache, update_ublock):
    """ Reset the browser to the default state. """

    driver.quit()
    driver = build_driver(cache, update_ublock, process)
    while not driver:
        driver = build_driver(cache, update_ublock, process)
    driver.set_page_load_timeout(30)
    return driver


def visit_site(db, process, driver, domain, url, temp_folder, cache, update_ublock, geo_db):
    """ Loads the website and extract its information. """

    links = []
    policy_links = []
    # Save uBlock tab info to get back when needed
    try:
        blocker_tab_handle = driver.current_window_handle
    except Exception as e:
        logger.error("Error saving uBlock tab: %s [Worker %d]" % (str(e), process))
        driver = reset_browser(driver, process, cache, update_ublock)
        return driver, FAILED, REPEAT, links, policy_links
    try:
        driver.execute_script('''window.open();''')
        second_tab_handle = driver.window_handles[-1]
        driver.switch_to.window(second_tab_handle)
    except WebDriverException as e:
        logger.error("WebDriverException (1) on %s / Error: %s [Worker %d]" % (domain.values["name"], str(e), process))
        driver = reset_browser(driver, process, cache, update_ublock)
        return driver, FAILED, REPEAT, links, policy_links

    logger.info('[Worker %d] URL: %s' % (process, url))
    # Load the website and wait some time inside it
    try:
        driver.get(url)
    except TimeoutException:
        logger.warning("Site %s timed out [Worker %d]" % (domain.values["name"], process))
        driver.close()
        driver.switch_to.window(blocker_tab_handle)
        try:
            storage = SessionStorage(driver)
            storage.clear()
        except NoSuchWindowException as e:
            logger.error("[Worker %d] Error accessing the session storage: %s" % (process, str(e)))
            driver = reset_browser(driver, process, cache, update_ublock)
        except WebDriverException as e:
            logger.error("[Worker %d] Error clearing session storage: %s" % (process, str(e)))
            driver = reset_browser(driver, process, cache, update_ublock)
        return driver, FAILED, REPEAT, links, policy_links
    except WebDriverException as e:
        # Remove Stacktrace for readability -- Most of the time this error is launched when visiting
        # a domain with no webpage associated -- The old log message should be used in production
        stacktrace_start = str(e).find("Stacktrace:")
        if stacktrace_start != -1:
            error_str = str(e)[:stacktrace_start].replace('\n','')
        else:
            error_str = str(e)
        logger.warning("WebDriverException (2) on %s / Error: %s (proc. %d)" % (domain.values["name"], error_str, process))

        driver = reset_browser(driver, process, cache, update_ublock)
        domain.values["update_timestamp"] = utc_now()
        domain.values["priority"] = 0
        domain.save()
        return driver, FAILED, NO_REPEAT, links, policy_links
    except Exception as e:
        logger.error("%s [Worker %d]" % (str(e), process))
        driver = reset_browser(driver, process, cache, update_ublock)
        domain.values["update_timestamp"] = utc_now()
        domain.values["priority"] = 0
        domain.save()
        return driver, FAILED, NO_REPEAT, links, policy_links

    # Wait some time inside the website
    time.sleep(10)
    window_handles = len(driver.window_handles)

    link = ""
    # Search for consent manager specific buttons
    elements = find_cmp_button(driver, process)
    # If not found search for cookies config buttons
    if not elements[0]:
        elements = find_cmp_config(driver, process)
        for element in elements[0]:
            if click_element(driver, element, elements[1], process):
                # If opened in new window add it to also download it
                if len(driver.window_handles) > window_handles:
                    link = element.get_attribute('href')
                    if link:
                        link = link.split("#")[0]
                        while link and link[0] == " ":
                            link = link[1:]
                        # If it is a malformed link try to fix it by adding the hosting domain
                        if link and link[0] == '/':
                            link = url.split(extract_domain(url))[0] + extract_domain(url) + link
                        elif link and link[0] != "h" and 1 < len(link.split("/")[0].split(".")) < 4:
                            link = "http://" + link
                        elif link and link[0:4] != 'http':
                            link = url.split(extract_domain(url))[0] + extract_domain(url) + '/' + link
                        policy_links.append(link)
                    driver.switch_to.window(driver.window_handles[-1])
                    driver.close()
                    driver.switch_to.window(driver.window_handles[1])
                else: # If not new window search for consent manager specific buttons
                    elements2 = find_cmp_button(driver, process)
                    for element2 in elements2[0]:
                        if click_element(driver, element2, elements2[1], process):
                            # If opened in new window add it to also download it
                            if len(driver.window_handles) > window_handles:
                                link = element2.get_attribute('href')
                                if link:
                                    link = link.split("#")[0]
                                    while link and link[0] == " ":
                                        link = link[1:]
                                    # If it is a malformed link try to fix it by adding the hosting domain
                                    if link and link[0] == '/':
                                        link = url.split(extract_domain(url))[0] + extract_domain(url) + link
                                    elif link and link[0] != "h" and 1 < len(link.split("/")[0].split(".")) < 4:
                                        link = "http://" + link
                                    elif link and link[0:4] != 'http':
                                        link = url.split(extract_domain(url))[0] + extract_domain(url) + '/' + link
                                    policy_links.append(link)
                                driver.switch_to.window(driver.window_handles[-1])
                                driver.close()
                                driver.switch_to.window(driver.window_handles[1])
    else:
        clicked = False
        for element in elements[0]:
            if click_element(driver, element, elements[1], process):
                clicked = True
                # If opened in new window add it to also download it
                if len(driver.window_handles) > window_handles:
                    link = element.get_attribute('href')
                    if link:
                        link = link.split("#")[0]
                        while link and link[0] == " ":
                            link = link[1:]
                        # If it is a malformed link try to fix it by adding the hosting domain
                        if link and link[0] == '/':
                            link = url.split(extract_domain(url))[0] + extract_domain(url) + link
                        elif link and link[0] != "h" and 1 < len(link.split("/")[0].split(".")) < 4:
                            link = "http://" + link
                        elif link and link[0:4] != 'http':
                            link = url.split(extract_domain(url))[0] + extract_domain(url) + '/' + link
                        policy_links.append(link)
                    driver.switch_to.window(driver.window_handles[-1])
                    driver.close()
                    driver.switch_to.window(driver.window_handles[1])
                if not clicked:
                    elements = find_cmp_config(driver, process)
                    for element in elements[0]:
                        if click_element(driver, element, elements[1], process):
                            # If opened in new window add it to also download it
                            if len(driver.window_handles) > window_handles:
                                link = element.get_attribute('href')
                                if link:
                                    link = link.split("#")[0]
                                    while link and link[0] == " ":
                                        link = link[1:]
                                    # If it is a malformed link try to fix it by adding the hosting domain
                                    if link and link[0] == '/':
                                        link = url.split(extract_domain(url))[0] + extract_domain(url) + link
                                    elif link and link[0] != "h" and 1 < len(link.split("/")[0].split(".")) < 4:
                                        link = "http://" + link
                                    elif link and link[0:4] != 'http':
                                        link = url.split(extract_domain(url))[0] + extract_domain(url) + '/' + link
                                    policy_links.append(link)
                                driver.switch_to.window(driver.window_handles[-1])
                                driver.close()
                                driver.switch_to.window(driver.window_handles[1])
                            else: # If not new window search for consent manager specific buttons
                                elements2 = find_cmp_button(driver, process)
                                for element2 in elements2[0]:
                                    if click_element(driver, element2, elements2[1], process):
                                        # If opened in new window add it to also download it
                                        if len(driver.window_handles) > window_handles:
                                            link = element2.get_attribute('href')
                                            if link:
                                                link = link.split("#")[0]
                                                while link and link[0] == " ":
                                                    link = link[1:]
                                                # If it is a malformed link try to fix it by adding the hosting domain
                                                if link and link[0] == '/':
                                                    link = url.split(extract_domain(url))[0] + extract_domain(url) + link
                                                elif link and link[0] != "h" and 1 < len(link.split("/")[0].split(".")) < 4:
                                                    link = "http://" + link
                                                elif link and link[0:4] != 'http':
                                                    link = url.split(extract_domain(url))[0] + extract_domain(url) + '/' + link
                                                policy_links.append(link)
                                            driver.switch_to.window(driver.window_handles[-1])
                                            driver.close()
                                            driver.switch_to.window(driver.window_handles[1])

    # We collect again the URL after redirections
    original_url = url
    url = driver.current_url
    
    # Collect website code and screenshot
    os.makedirs(os.path.join(os.path.abspath("."), temp_folder), exist_ok=True)
    try:
        webcode = driver.page_source
    except InvalidArgumentException as e:
        logger.warning("InvalidArgumentException on %s / Error: %s [Worker %d]" % (domain.values["name"], str(e), process))
        driver = reset_browser(driver, process, cache, update_ublock)
        domain.values["update_timestamp"] = utc_now()
        domain.values["priority"] = 0
        domain.save()
        return driver, FAILED, REPEAT, links, policy_links
    except WebDriverException as e:
        logger.warning("WebDriverException (3) on %s / Error: %s [Worker %d]" % (domain.values["name"], str(e), process))
        driver = reset_browser(driver, process, cache, update_ublock)
        domain.values["update_timestamp"] = utc_now()
        domain.values["priority"] = 0
        domain.save()
        return driver, FAILED, REPEAT, links, policy_links
    except Exception as e:
        logger.error("%s [Worker %d]" % (str(e), process))
        driver = reset_browser(driver, process, cache, update_ublock)
        domain.values["update_timestamp"] = utc_now()
        domain.values["priority"] = 0
        domain.save()
        return driver, FAILED, REPEAT, links, policy_links

    compressed_screenshot = None
    size = 0
    if not domain.values["screenshot"]:
        filename = os.path.join(temp_folder, domain.values["name"] + 'ss.png')
        driver.save_screenshot(filename)
        if os.path.isfile(os.path.join(temp_folder, domain.values["name"] + 'ss.png')):
            size = os.stat(filename).st_size
        if size > 0:
            # Compress the screenshot to save it into the database when needed
            with open(filename, 'rb') as f:
                blob_value = f.read()
                compressed_screenshot = zlib.compress(blob_value)
        if os.path.isfile(os.path.join(temp_folder, domain.values["name"] + 'ss.png')):
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
        logger.warning("WebDriverException (3) on %s / Error: %s [Worker %d]" % (domain.values["name"], str(e), process))
        driver = reset_browser(driver, process, cache, update_ublock)
        return driver, FAILED, REPEAT, links, policy_links

    # Process traffic from uBlock Origin tab sessionStorage
    try:
        driver.switch_to.window(blocker_tab_handle)
    except Exception as e:
        logger.error("Error accessing uBlock tab: %s [Worker %d]" % (str(e), process))
        driver = reset_browser(driver, process, cache, update_ublock)
        return driver, FAILED, REPEAT, links, policy_links
    try:
        storage = SessionStorage(driver)
        web_list = {}
        for key in storage.keys():
            web_list[key] = storage[key]
    except NoSuchWindowException as e:
        logger.error("[Worker %d] Error accessing the session storage: %s" % (process, str(e)))
        driver = reset_browser(driver, process, cache, update_ublock)
        return driver, FAILED, REPEAT, links, policy_links
    else:
        # Insert data and clear storage before opening the next website
        manage_requests(db, process, domain, web_list, temp_folder, geo_db)
        links = parse_internal_links(url, webcode)
        try:
            storage.clear()
        except WebDriverException as e:
            logger.error("[Worker %d] Error clearing session storage: %s" % (process, str(e)))
            driver = reset_browser(driver, process, cache, update_ublock)
            return driver, FAILED, NO_REPEAT, links, policy_links
    
    if link:
        links.append(link)    
    # Save the screenshot and update the db update timestamp
    domain.values["update_timestamp"] = utc_now()
    domain.values["priority"] = 0
    if compressed_screenshot:
        domain.values["screenshot"] = compressed_screenshot
    domain.save()
    return driver, COMPLETED, NO_REPEAT, links, policy_links

def find_element_in_content(driver, process, extra_texts=[]):
    shadow = Shadow(driver)
    possible_texts = ["cookies de terceros", 
                      "third-party cookies", 
                      "customize partners",
                      "customize purposes",
                      "drittanbieter",
                      "list of partners",
                      "list of partners (vendors)",
                      "list of partners (service providers or vendors)",
                      "lista de asociados (proveedores)",
                      "lista de socios (proveedores)",
                      "nuestros socios",
                      "other companies",
                      "our partners",
                      "our third party partners",
                      "partner",
                      "partenaires",
                      "show purposes",
                      "storage preferences",
                      "technology partners",
                      "third-party companies",
                      "third party partners",
                      "third parties",
                      "vendors",
                      "ver nuestros socios",
                      "ver partners",
                      "veure els nostres socis",
                      "view cookie settings",
                      "view cookies",
                      "view our partners",
                      "voir nos partenaires",
                      "non-iab",
                      "iab partners"]
    possible_xpaths = ['//button[normalize-space(translate(descendant::*[last()]/text(), \'ABCDEFGHIJKLMNOPQRSTUVWXYZ\', \'abcdefghijklmnopqrstuvwxyz\')) = \'%s\']',
                       '//a[normalize-space(translate(descendant::*[last()]/text(), \'ABCDEFGHIJKLMNOPQRSTUVWXYZ\', \'abcdefghijklmnopqrstuvwxyz\')) = \'%s\']',
                       '//button[translate(normalize-space(text()), \'ABCDEFGHIJKLMNOPQRSTUVWXYZ\', \'abcdefghijklmnopqrstuvwxyz\')= \'%s\']',
                       '//a[translate(normalize-space(text()), \'ABCDEFGHIJKLMNOPQRSTUVWXYZ\', \'abcdefghijklmnopqrstuvwxyz\')= \'%s\']']
    search_results = []

    for xpath in possible_xpaths:
        texts = possible_texts + extra_texts
        for i in range(len(texts)):
            text = texts[i]
#            logger.info(f"Searching for element with XPATH selector: %s" % text)
            elements = shadow.find_elements_by_xpath(xpath % text, True)

            for element in elements:
                found = False
                for element2 in search_results:
                    if element.id == element2.id:
                        found = True
                if not found:
                    # Order the found elements with the most important first
                    if i <= 25:
                        search_results.insert(0, element)
                    else:
                        search_results.append(element)
                    logger.info("[Worker %d] CMP Checker: Element found with XPATH selector %s" % (process, text))

    return search_results

def find_config_in_content(driver, process, extra_texts=[]):
    shadow = Shadow(driver)
    possible_texts = ["administrar las cookies y obtener más información",
                     "adjust settings",
                     "administrar",
                     "administrar cookies",
                     "advanced",
                     "ajuste de cookies",
                     "ajustes",
                     "ajustes de cookies",
                     "ajuste sus preferencias",
                     "centro de privacidad",
                     "change settings",
                     "click here",
                     "configuración de cookies",
                     "configurar",
                     "cookie consent manager",
                     "cookie consent tool",
                     "cookie details",
                     "cookie preferences",
                     "cookie settings",
                     "cookie settings page",
                     "cookies details",
                     "cookies settings",
                     "customise",
                     "customise my choices",
                     "customise cookie preferences",
                     "customise third-party cookies",
                     "customize",
                     "customize settings",
                     "en savoir plus",
                     "elección de cookies",
                     "gestionar cookies",
                     "gestionar las cookies",
                     "gestionar configuración de privacidad",
                     "here",
                     "manage",
                     "manage choices",
                     "manage cookie settings",
                     "manage cookies",
                     "manage options",
                     "manage preferences",
                     "manage privacy settings",
                     "manage settings",
                     "manage your cookies",
                     "manage your cookie preferences",
                     "manage your tracker settings",
                     "más información",
                     "més informació",
                     "more options",
                     "more choices",
                     "options",
                     "panel de configuración",
                     "paramétrer",
                     "paramétrer les cookies",
                     "personalizar cookies",
                     "personalize",
                     "privacy center",
                     "set cookie options",
                     "set up",
                     "settings",
                     "show details",
                     "update settings",
                     "información de las cookies",
                     "privacy policy",
                     "cookie policy"]
    possible_xpaths = ['//button[normalize-space(translate(descendant::*[last()]/text(), \'ABCDEFGHIJKLMNOPQRSTUVWXYZ\', \'abcdefghijklmnopqrstuvwxyz\')) = \'%s\']',
                       '//a[normalize-space(translate(descendant::*[last()]/text(), \'ABCDEFGHIJKLMNOPQRSTUVWXYZ\', \'abcdefghijklmnopqrstuvwxyz\')) = \'%s\']',
                       '//button[translate(normalize-space(text()), \'ABCDEFGHIJKLMNOPQRSTUVWXYZ\', \'abcdefghijklmnopqrstuvwxyz\')= \'%s\']',
                       '//a[translate(normalize-space(text()), \'ABCDEFGHIJKLMNOPQRSTUVWXYZ\', \'abcdefghijklmnopqrstuvwxyz\')= \'%s\']']
    search_results = []
    for xpath in possible_xpaths:
        texts = possible_texts + extra_texts
        for i in range(len(texts)):
            text = texts[i]
#            logger.info(f"Searching for element with XPATH selector: %s" % text)
            elements = shadow.find_elements_by_xpath(xpath % text, True)

            for element in elements:
                found = False
                for element2 in search_results:
                    if element.id == element2.id:
                        found = True
                if not found:
                    # Order the found elements with the most important first
                    search_results.append(element)
                    logger.info("[Worker %d] CMP Checker: Config found with XPATH selector %s" % (process, text))

    return search_results

def find_iframes(driver):
    shadow = Shadow(driver)
    elements = []
    iter_elements = shadow.find_elements_by_xpath("//iframe", True)
    if iter_elements:
        elements.extend(iter_elements)
    return elements


def find_cmp_button(driver, process):
    elements = find_element_in_content(driver, process)

    if not elements:
        logger.info("[Worker %d] CMP Checker: Element not found, searching in iframes" % (process))
        iframes = find_iframes(driver)
        if iframes:
            for iframe in iframes:
                iframe_id = iframe.get_attribute("id")
                if not iframe_id:
                    continue
                driver.switch_to.frame(iframe.get_attribute("id"))
                elements = find_element_in_content(driver, process, ["partners"])
                driver.switch_to.default_content()
                if elements:
                    logger.info("[Worker %d] CMP Checker: Element found iun iframe %d" % (process, iframe_id))
                    return [elements, iframe_id]
    return [elements, 0]

def find_cmp_config(driver, process):
    logger.info("[Worker %d] CMP Checker: Element not found, searching for config elements" % (process))
    elements = find_config_in_content(driver, process)

    if not elements:
        logger.info("[Worker %d] CMP Checker: Config not found, searching in iframes" % (process))
        iframes = find_iframes(driver)
        if iframes:
            for iframe in iframes:
                iframe_id = iframe.get_attribute("id")
                if not iframe_id:
                    continue
                driver.switch_to.frame(iframe.get_attribute("id"))
                elements = find_config_in_content(driver, process, ["learn more"])
                driver.switch_to.default_content()
                if elements:
                    logger.info("[Worker %d] CMP Checker: Config found in iframes %d" % (process, iframe_id))
                    return [elements, iframe_id]
    return [elements, 0]

def click_element(driver, element, iframe, process):
    done = True
    if iframe:
        driver.switch_to.frame(iframe)
    try:
        element.click()
        # Wait some time to load new resources
        time.sleep(10)
    except ElementNotInteractableException as e:
        logger.info("[Worker %d] CMP Checker: Element not interactable" % (process))
        done = False
    except ElementClickInterceptedException as e:
        logger.info("[Worker %d] CMP Checker: Element intercepted" % (process))
        done = False
    except StaleElementReferenceException as e:
        logger.info("[Worker %d] CMP Checker: Element staled" % (process))
        done = False
    except NoSuchElementException as e:
        logger.info("[Worker %d] CMP Checker: Element not present" % (process))
        done = False
    if iframe:
        driver.switch_to.default_content()
    return done
