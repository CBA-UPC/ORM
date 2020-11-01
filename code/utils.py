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

import socket
from datetime import datetime, timezone
from urllib.parse import urlparse
import config

import tldextract
from geoip2 import database
from geoip2.errors import AddressNotFoundError

import requests
from hashlib import sha256

try:
    import tlsh

    tlsh_func = tlsh.hash
except ImportError:
    RuntimeWarning('You will have to install tlsh python extension manually'
                   ' (https://github.com/trendmicro/tlsh) to get local space hashing functionality')
    tlsh_func = lambda x: ''


def utc_now():
    """ Returns the current time in MySQL compatible format. """

    ts = datetime.now(timezone.utc).timestamp()
    return datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')


def extract_address(url):
    """ Extract IP address from URL. """

    url = extract_domain(url)
    address = None
    fails = 0
    while not address and fails < 10:
        try:
            address = socket.gethostbyname(url)
        except Exception as e:
            fails += 1
    return address


def extract_domain(url):
    """ Extract domain from URL. """

    return urlparse(url).hostname


def clean_subdomain(url):
    """ Extracts the base domain (without subdomain) from the URL. """

    extracted_domain = tldextract.extract(url)
    domain = extracted_domain[1]
    if extracted_domain[2]:
        domain = domain + "." + extracted_domain[2]
    return domain


def extract_components(url):
    """ Returns a dict with the URL components. """

    parsed = urlparse(url)
    components = {'scheme': parsed.scheme, 'netloc': parsed.netloc, 'path': parsed.path, 'params': parsed.params,
                  'query': parsed.query, 'fragment': parsed.fragment, 'username': parsed.username,
                  'password': parsed.password, 'hostname': parsed.hostname, 'port': parsed.port}
    return components


def extract_location(address, reader=None):
    """ Extract country from URL. """

    location = {'continent_code': None, 'country_code': None, 'is_EU': 0, 'city': None,
                'latitude': 0, 'longitude': 0, 'accuracy_radius': 0}
    if address:
        if not reader:
            reader = database.Reader(config.CITY_FILE_PATH)
        try:
            response = reader.city(address)
        except AddressNotFoundError:
            pass
        else:
            location['continent_code'] = response.continent.code
            location['country_code'] = response.country.iso_code
            location['is_EU'] = response.country.is_in_european_union
            location['city'] = response.city.name
            location['latitude'] = response.location.latitude
            location['longitude'] = response.location.longitude
            location['accuracy_radius'] = response.location.accuracy_radius
    return location


def download_file(url, destination, headers=None, verify=True):
    """ Downloads a file. """

    h = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:45.0) Gecko/20100101 Firefox/45.0'}
    if headers is not None:
        h.update(headers)

    resp = requests.get(url, stream=True, headers=h, timeout=(6, 27), verify=verify)
    for chunk in resp.iter_content(chunk_size=4096):
        if chunk:
            destination.write(chunk)

    destination.seek(0)
    return destination, resp.headers


def lsh_file(filename):
    """ Calculates the tlsh (fuzzy matching hash) of a file. """

    with open(filename, 'rb') as f:
        return tlsh_func(f.read())


def hash_file(filename, hash_func=sha256):
    """ Calculates SHA256 of a file. """

    h = hash_func()
    with open(filename, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            h.update(chunk)

    return h.hexdigest()


def hash_string(s, hash_func=sha256):
    """ Calculates SHA256 of a string. """

    h = hash_func(s.encode())
    return h.hexdigest()
