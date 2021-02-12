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
import os
import time
import json
import shutil
import logging
import logging.config

# 3rd party modules
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException
from selenium.common.exceptions import UnexpectedAlertPresentException, InvalidSessionIdException, NoSuchFrameException

# Own modules
import config
from data_manager import get_network, manage_request, get_performance

logging.config.fileConfig('../logging.conf')

logger = logging.getLogger("DRIVER_MANAGER")


def build_driver(plugin, cache, process):
    """ Creates the selenium driver to be used by the script and loads the corresponding plugin if needed. """

    try:
        chrome_options = webdriver.ChromeOptions()
        # chrome_options.add_argument('--headless')
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

        # Set Devtools Protocol to start taking network performance logs
#        chrome_options.set_capability("loggingPrefs", {'performance': 'ALL'})
#        chrome_options.add_experimental_option('w3c', False)
        # Set Devtools Protocol to start taking trace logs
        #        chrome_options.add_argument('--enable-gpu-benchmarking')
#        chrome_options.add_argument('--enable-thread-composting')
#        chrome_options.add_argument('--enable-service-manager-tracing')
#        chrome_options.add_argument('--enable-gpu-client-tracing')
#        chrome_options.add_experimental_option("perfLoggingPrefs", {
#            "traceCategories": "__metadata,"
#                               "loading,"
#                               "v8,"
#                               "devtools.timeline,"
#                               "disabled-by-default-devtools.timeline",
#            "enableNetwork": True,
#            "enablePage": True
#        })

        # Load received plugin (except for vanilla)
        if plugin.values["name"] != "Vanilla":
            chrome_options.add_extension(plugin.values['path'])
        driver = webdriver.Chrome(chrome_options=chrome_options)
        capabilities = str(list((driver.desired_capabilities.values())))
        port = int(capabilities.split('localhost:')[1].split("'", 1)[0])
        if plugin.values["name"] != "Vanilla" and plugin.values['custom']:
            time.sleep(3)
            driver.get(plugin.values['url'])
            time.sleep(10)
            try:
                driver.find_element_by_xpath(plugin.values['xpath_to_click']).click()
            except NoSuchElementException as e:
                driver.switch_to.frame(0)
                driver.find_element_by_xpath(plugin.values['xpath_to_click']).click()
            time.sleep(20)
            driver.switch_to.window(driver.window_handles[0])
#            driver.close()
#            driver.switch_to.window(driver.window_handles[0])
        return driver, port
    except Exception as e:
        # logger.error(e)
        logger.error("(proc. %d) Error creating driver: %s" % (process, str(e)))
        return 0, 0


def reset_browser(driver, process, plugin, cache):
    """ Reset the browser to the default state. """

    port = 0
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
            driver, port = build_driver(plugin, cache, process)
            while not driver:
                driver, port = build_driver(plugin, cache, process)
            driver.set_page_load_timeout(30)
    except Exception as e:
        logger.error("(proc. %d) Error #5: %s" % (process, str(e)))
        try:
            driver.close()
        except InvalidSessionIdException as e:
            logger.error("(proc. %d) Error #6: %s" % (process, str(e)))
        driver, port = build_driver(plugin, cache, process)
        while not driver:
            driver, port = build_driver(plugin, cache, process)
        driver.set_page_load_timeout(30)
    return driver, port


def visit_site(db, process, driver, port, domain, plugin, temp_folder, cache):
    """ Loads the website and extract its information. """

    desktop = True
    trace_path = os.path.join(os.path.abspath(temp_folder), str(port))
    os.makedirs(trace_path, exist_ok=True)
    # Load the website and wait some time inside it
    command = 'lighthouse %s' % ('http://' + domain.values["name"])
    command += ' -G -A=%s --port=%d' % (trace_path, port)
    command += ' --quiet --no-update-notifier'
    command += ' --emulatedUserAgent=false'
    command += ' --output=json --output-path=%s' % os.path.join(trace_path, "main.json")
    if desktop:
        command += ' --preset=desktop --throttling.cpuSlowdownMultiplier=0'
        command += ' --screenEmulation.width=1920 --screenEmulation.height=1080'
    else:
        command += ' --throttling.cpuSlowdownMultiplier=1'
    stream = os.popen(command)
    max_retries = 120
    log_file = os.path.join(trace_path, 'lhr.report.json')
    trace_file = os.path.join(trace_path, 'defaultPass.devtoolslog.json')
    retries = 0
    while not os.path.isfile(log_file) and retries < max_retries:
        retries += 1
        time.sleep(1)
    if stream.close():
        logger.error("(proc. %d) Lighthouse error on website %s" % (process, domain.values["name"]))
        return driver
    with open(trace_file, "r") as f:
        trace = json.load(f)
        network_traffic = get_network(trace)
        # logger.debug("(proc. %d) Extracted data: %s" % (process, str(network_traffic)))
        # Process traffic dictionary
        for key in network_traffic.keys():
            manage_request(db, domain, network_traffic[key], plugin)
            for sub_key in network_traffic[key]["requests"].keys():
                manage_request(db, domain, network_traffic[key]["requests"][sub_key], plugin)
        with open(log_file, "r") as f2:
            log = json.load(f2)
            get_performance(db, domain, plugin, log, process)

    shutil.rmtree(trace_path)
    driver, port = reset_browser(driver, process, plugin, cache)
    return driver
