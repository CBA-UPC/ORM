'''
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
'''

# -*- coding: utf-8 -*-

# Basic modules
import time
import logging
import logging.config

# 3rd party modules
from setproctitle import setproctitle
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.common.exceptions import UnexpectedAlertPresentException, InvalidSessionIdException

# Own modules
import config
from data_manager import get_network, manage_request

logging.config.fileConfig('../logging.conf')

logger = logging.getLogger("DRIVER_MANAGER")


def build_driver(plugin, cache, process):
    """ Creates the selenium driver to be used by the script and loads the corresponding plugin if needed. """

    try:
        chrome_options = webdriver.ChromeOptions()
        # Clean cache/cookies if not specified to maintain
        if not cache:
            chrome_options.add_argument('--media-cache-size=0')
            chrome_options.add_argument('--v8-cache-options=off')
            chrome_options.add_argument('--disable-gpu-program-cache')
            chrome_options.add_argument('--gpu-program-cache-size-kb=0')
            chrome_options.add_argument('--disable-gpu-shader-disk-cache')
            chrome_options.add_argument('--disk-cache-dir=/tmp')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--v8-cache-strategies-for-cache-storage=off')
            chrome_options.add_argument('--mem-pressure-system-reserved-kb=0')
            chrome_options.set_capability("applicationCacheEnabled", False)
            chrome_options.add_extension(config.CLEANER_PLUGIN_PATH)

        # Set Devtools Protocol to start taking network logs
        chrome_options.set_capability("loggingPrefs", {'performance': 'ALL'})
        chrome_options.add_experimental_option('w3c', False)

        # Load received plugin (except for vanilla)
        if plugin.values["name"] != "Vanilla":
            chrome_options.add_extension(plugin.values['path'])
        driver = webdriver.Chrome(options=chrome_options)
        if plugin.values["name"] != "Vanilla" and plugin.values['custom']:
            driver.get(plugin.values['url'])
            time.sleep(3)
            driver.switch_to.frame(0)
            driver.find_element_by_xpath(plugin.values['xpath_to_click']).click()
            time.sleep(20)
            driver.switch_to.window(driver.window_handles[0])
#            driver.close()
#            driver.switch_to.window(driver.window_handles[0])
        return driver
    except Exception as e:
        # logger.error(e)
        logger.error("(proc. %d) Error creating driver: %s" % (process, str(e)))
        return 0


def reset_browser(driver, process, plugin, cache):
    """ Reset the browser to the default state. """

    try:
        driver.switch_to.default_content()
        if not cache:
            driver.delete_all_cookies()
    except UnexpectedAlertPresentException:
        try:
            alert = driver.switch_to.alert
            alert.dismiss()
        except Exception as e:
            # logger.error(e)
            logger.error("(proc. %d) Error #4: %s" % (process, str(e)))
            driver.close()
            driver = build_driver(plugin, cache, process)
            while not driver:
                driver = build_driver(plugin, cache, process)
            driver.set_page_load_timeout(30)
    except InvalidSessionIdException as e:
        logger.error("(proc. %d) Error #6: %s" % (process, str(e)))
        driver = build_driver(plugin, cache, process)
        while not driver:
            driver = build_driver(plugin, cache, process)
        driver.set_page_load_timeout(30)
    except Exception as e:
        logger.error("(proc. %d) Error #5: %s" % (process, str(e)))
        driver.close()
        driver = build_driver(plugin, cache, process)
        while not driver:
            driver = build_driver(plugin, cache, process)
        driver.set_page_load_timeout(30)
    return driver


def visit_site(db, process, driver, domain, plugin, temp_folder, cache):
    """ Loads the website and extract its information. """

    # Load the website and wait some time inside it
    setproctitle(domain.values["name"])
    try:
        driver.get('http://' + domain.values["name"])
    except TimeoutException:
        logger.warning("Site %s timed out (proc. %d)" % (domain.values["name"], process))
        driver.close()
        driver = build_driver(plugin, cache, process)
        while not driver:
            driver = build_driver(plugin, cache, process)
        driver.set_page_load_timeout(30)
        return driver, True
    except WebDriverException as e:
        logger.warning("WebDriverException on site %s / Error: %s (proc. %d)" % (domain.values["name"], str(e),
                                                                                  process))
        driver = reset_browser(driver, process, plugin, cache)
        return driver, True
    except Exception as e:
        logger.error("%s (proc. %d)" % (str(e), process))
        driver = reset_browser(driver, process, plugin, cache)
        return driver, True
    time.sleep(10)

    # Get network traffic dictionary
    # logger.debug(driver.log_types)
    log_entries = driver.get_log('performance')
    # logger.debug("(proc. %d) Network data: %s" % (process, str(log_entries)))
    network_traffic = get_network(log_entries)
    # logger.debug("(proc. %d) Extracted data: %s" % (process, str(network_traffic)))

    # Process traffic dictionary
    for key in network_traffic.keys():
        manage_request(db, process, domain, network_traffic[key], plugin, temp_folder)
        for sub_key in network_traffic[key]["requests"].keys():
            manage_request(db, process, domain, network_traffic[key]["requests"][sub_key], plugin, temp_folder)

    driver = reset_browser(driver, process, plugin, cache)
    return driver, False
