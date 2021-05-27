# Basic modules
import os
import re
import json
import logging
import logging.config
import argparse
import zlib
import mmap
import time
from datetime import datetime, timezone, timedelta

# 3rd party modules
from dateutil import parser

# Own modules
from db_manager import Db, Connector
from utils import hash_string, utc_now, extract_domain

logging.config.fileConfig('logging.conf')

logger = logging.getLogger("TRACKING_MANAGER")

mouseEvents = ["scroll", "drag", "dragend", "dragstart", "dragleave", "dragover", "drop",
               "mozInputSource", "buttons", "movementX", "movementY", "mozPressure", "pressure",
               "deltaX", "deltaY", "deltaZ", "deltaWheel"]


def parse_cookies(cookie_string):
    """ Parses all the cookies of the given 'set-cookie' string """

    cookie_list = []
    allowed_values = ["expires", "max-age", "domain", "path", "samesite", "secure", "httponly"]
    cookie_lines = cookie_string.split("\n")
    for cookie_line in cookie_lines:
        cookie_line = cookie_line.replace("; ", ";")
        parameters = cookie_line.split(";")
        for parameter in parameters:
            if len(parameter) == 0:
                continue
            parameter_list = parameter.split("=", maxsplit=1)
            key = parameter_list[0].lower()
            if key not in allowed_values:
                # If it is not one of the default values is a new cookie
                if len(parameter_list[1]) == 0:
                    cookie_list.append({"name": parameter_list[0], "value": None})
                else:
                    cookie_list.append({"name": parameter_list[0], "value": parameter_list[1]})
            elif key == "expires":
                # Create 'datetime' object from expire value
                cookie_list[-1][key] = parser.parse(parameter_list[1])
            elif key == "max-age":
                # Compute expire 'datetime' object from current time + max-age value
                now = datetime.now(timezone.utc)
                cookie_list[-1][key] = now + timedelta(seconds=int(parameter_list[1]))
            else:
                # For the rest of the values we save them unmodified
                for value in allowed_values:
                    if key == value:
                        if key in ["secure", "httponly"]:
                            cookie_list[-1][key] = True
                        else:
                            cookie_list[-1][value] = parameter_list[1]

    # Discard bad formatted cookies or values
    final_cookie_list = []
    for cookie in cookie_list:
        if ("expires" in cookie.keys() or "max-age" in cookie.keys()) and cookie["value"]:
            final_cookie_list.append(cookie)

    return final_cookie_list


def check_cookies(cookie_list, domain):
    """ Checks a cookie list to find tracking cookies """

    # Compute periods
    now = datetime.now(timezone.utc)
    three_months = now + timedelta(days=90)
    one_year = now + timedelta(days=365)

    # Check cookies
    for cookie in cookie_list:
        is_third_party = False
        if "domain" in cookie.keys() and cookie["domain"].find(domain.values["name"]) == -1:
            is_third_party = True
        # Check first 'max-age' value as it has preference over 'expires'
        expire_value = "expires"
        if "max-age" in cookie.keys():
            expire_value = "max-age"
        if expire_value in cookie.keys():
            if cookie[expire_value] > one_year:
                cookie["tracking"] = "Very long-living cookies"
            elif cookie[expire_value] > three_months and not is_third_party:
                cookie["tracking"] = "Long-living cookies"
            elif cookie[expire_value] > three_months and is_third_party:
                cookie["tracking"] = "Tracking cookies"
            elif is_third_party:
                cookie["tracking"] = "Third-party cookies"
            elif not is_third_party:
                cookie["tracking"] = "Session cookies"
    return cookie_list


def get_http_cookies(url, main_domain):
    """ Get all the cookies included on the HTTP request of a given URL """

    # If not HTTP headers in DB return empty dict
    if "response_headers" not in url.values.keys() or not url.values["response_headers"]:
        return {}

    # Get url info
    db = url.db
    headers = json.loads(url.values["response_headers"])

    # Check cookies
    http_cookies = []
    if "set-cookie" in headers.keys():
        http_cookies = parse_cookies(headers["set-cookie"])
    elif "Set-Cookie" in headers.keys():
        http_cookies = parse_cookies(headers["Set-Cookie"])
    http_cookies = check_cookies(http_cookies, main_domain)

    # Insert cookie info in DB
    tracking_list = {}
    for cookie in http_cookies:
        if "tracking" in cookie.keys():
            if cookie["tracking"] not in tracking_list.keys():
                tracking_list[cookie["tracking"]] = 1
            else:
                tracking_list[cookie["tracking"]] += 1
    for tracking_value in tracking_list.keys():
        tracking = Connector(db, "tracking")
        tracking.load(hash_string(tracking_value))
        url.add(tracking, {"quantity": tracking_list[tracking_value], "update_timestamp": utc_now()})
    return tracking_list


def get_js_cookies(url):
    """ Check JavaScript managed cookies. """

    # Get url info
    db = url.db

    # Finish if resource does not exist
    if not url.values["resource_id"]:
        return 0

    # Finish if we don't have the resource in the DB (we only save HTML and JS files)
    resource = Connector(db, "resource")
    resource.load(url.values["resource_id"])
    if not resource.values["file"]:
        return 0

    # Get tracking info
    tracking = Connector(db, "tracking")
    tracking.load(hash_string("JavaScript cookies"))

    # Return DB value if already computed
    tracking_list = resource.get("tracking", order="tracking_id")
    for tr in tracking_list:
        if tr.values["id"] == tracking.values["id"]:
            request = "SELECT quantity FROM resource_tracking WHERE resource_id = %d AND tracking_id = %d" % (
                resource.values["id"], tracking.values["id"])
            return db.custom(request)["quantity"]

    # Otherwise extract file and compute
    code = zlib.decompress(resource.values["file"])
    try:
        formatted_code = str(code, 'utf-8')
    except Exception as e:
        formatted_code = str(code)
    cookies = 0
    if formatted_code.find(".cookie=") != -1:
        cookies += len(formatted_code.split(".cookie=")) - 1

    # If tracking found, save inside DB
    if cookies > 0:
        url.add(tracking, {"quantity": cookies, "update_timestamp": utc_now()})
    return cookies


def get_font_fingerprinting(url):
    """ Get the number of fonts accessed inside the resource loaded by the given url. """

    # Get url info
    db = url.db
    fonts = Connector(db, "font")
    fonts = fonts.get_all()

    # Finish if resource does not exist
    if not url.values["resource_id"]:
        return 0

    # Finish if we don't have the resource in the DB (we only save HTML and JS files)
    resource = Connector(db, "resource")
    resource.load(url.values["resource_id"])
    if not resource.values["file"]:
        return 0

    # Get tracking info
    tracking = Connector(db, "tracking")
    tracking.load(hash_string("Font fingerprinting"))

    # Return DB value if already computed
    tracking_list = resource.get("tracking", order="tracking_id")
    for tr in tracking_list:
        if tr.values["id"] == tracking.values["id"]:
            request = "SELECT quantity FROM resource_tracking WHERE resource_id = %d AND tracking_id = %d" % (
                resource.values["id"], tracking.values["id"])
            return db.custom(request)["quantity"]

    # Otherwise extract file and compute
    code = zlib.decompress(resource.values["file"])
    try:
        formatted_code = str(code, 'utf-8')
    except Exception as e:
        formatted_code = str(code)
    file_fonts = 0
    file_offset_height = False
    file_offset_width = False
    for font in fonts:
        if formatted_code.find(font.values["name"]) != -1:
            file_fonts += 1
    if formatted_code.find(".offsetHeight") != -1:
        file_offset_height = True
    if formatted_code.find(".offsetWidth") != -1:
        file_offset_width = True

    # If tracking found, save inside DB
    if file_fonts > 28 and file_offset_height and file_offset_width:
        url.add(tracking, {"quantity": file_fonts, "update_timestamp": utc_now()})
    return file_fonts


def check_canvas_properties(code, prop_1, prop_2, prop_3):
    """ Searches for canvas fingerprint patterns based on given properties inside the give code"""

    # Initialize counting variables
    big = 0
    icon = 0

    # Search canvas string combination
    if code.find(prop_1) != -1 and code.find(prop_2) != -1 and code.find(prop_3) != -1:
        code_pieces = code.split(prop_2)
        skip_next = False
        for i in range(len(code_pieces)):
            # Avoid counting '-width:' and '-height:' values
            skip_current = False
            if i == 0 or skip_next:
                skip_current = True
                skip_next = False
            piece = code_pieces[i]
            if piece[-1] == "-" and prop_2[-1] == ":":
                skip_next = True
            if skip_current:
                continue

            # Get the integer value and skip percentages
            value = ""
            index = 0
            finished = False
            while not finished:
                last_value = piece[index]
                if last_value.isnumeric():
                    value += last_value
                    index += 1
                elif last_value == "\"":
                    index += 1
                else:
                    if last_value == "%":
                        value = ""
                    finished = True

            # Depending on the size account them as possible canvas fingerprinting
            if len(value) != 0:
                if int(value) >= 16:
                    if int(value) > 32:
                        big += 1
                    else:
                        icon += 1
    return big, icon


def get_canvas_fingerprinting(url):
    """ Checks if there is canvas fingerprinting inside the resource loaded by the given url. """

    # Get url info
    db = url.db

    # Finish if resource does not exist
    if not url.values["resource_id"]:
        return 0

    # Finish if we don't have the resource in the DB (we only save HTML and JS files)
    resource = Connector(db, "resource")
    resource.load(url.values["resource_id"])
    if not resource.values["file"]:
        return 0

    # Get tracking info
    tracking_big = Connector(db, "tracking")
    tracking_big.load(hash_string("Canvas fingerprinting (big)"))
    tracking_small = Connector(db, "tracking")
    tracking_small.load(hash_string("Canvas fingerprinting (small)"))

    # Return DB value if already computed
    tracking_list = resource.get("tracking", order="tracking_id")
    for tr in tracking_list:
        if tr.values["id"] == tracking_big.values["id"]:
            return 1
        elif tr.values["id"] == tracking_small.values["id"]:
            return 1

    # Otherwise extract file and compute
    code = zlib.decompress(resource.values["file"])
    try:
        formatted_code = str(code, 'utf-8')
    except Exception as e:
        formatted_code = str(code)

    code = formatted_code[:-1]
    code = code.replace("b'", "")
    code = code.replace("\\\\", "")
    code = code.replace("\\n", "")
    code = code.replace("\\'", "'")
    big_width, icon_width = check_canvas_properties(code, ".createElement(\"canvas\")", ".width=", ".toDataURL(")
    big_height, icon_height = check_canvas_properties(code, ".createElement(\"canvas\")", ".height=", ".toDataURL(")
    big_width2, icon_width2 = check_canvas_properties(code, ".createElement(\"canvas\")", "width:", ".toDataURL(")
    big_height2, icon_height2 = check_canvas_properties(code, ".createElement(\"canvas\")", "height:", ".toDataURL(")
    canvas1 = min(big_width, big_height) + min(big_width2, big_height2)
    canvas2 = min(icon_width, icon_height) + min(icon_width2, icon_height2)

    # If tracking found, save inside DB
    if canvas1:
        resource.add(tracking_big, {"quantity": canvas1, "update_timestamp": utc_now()})
    if canvas2:
        resource.add(tracking_small, {"quantity": canvas2, "update_timestamp": utc_now()})
    return canvas1, canvas2


def find_end(javascript_file, a, ini_label, end_label):
    """ Auxiliary function to find the end position of the code piece. """

    with open(javascript_file) as f:
        f.seek(a)
        nothing = 0
        while f.read(1) != ini_label:
            nothing += 1
            if nothing == 100:
                return 0
        val = 0
        end = False
        while not end:
            curr = f.read(1)
            if curr == ini_label:
                val += 1
            elif curr == end_label:
                if val == 0:
                    end = True
                    pos = f.tell()
                else:
                    val -= 1
    return pos


def ret_post(javascript_file, ini, end):
    """ Auxiliary function to find the mouse tracking returning point. """
    with open(javascript_file) as f:
        s = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        for tag in ['post', 'postMessage', 'sendMessage', 'ym']:
            ba = bytearray()
            ba.extend(map(ord, tag))
            try:
                if s.find(ba, ini, end) != -1:
                    return True
            except OverflowError as err:
                print("File too large")


def parse_mouse_fingerprinting(javascript_file):
    done = False
    with open(javascript_file) as f:
        try:
            html = f.read(len("<!DOCTYPE html>"))
            f.seek(0)
            if "<!" in html or "docty" in html:
                return False
        except UnicodeDecodeError as e:
            print("Probably not an UTF-8 file")
            return False
        f.seek(0)
        s = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        for event in mouseEvents:
            b = bytearray()
            c = bytearray()
            d = bytearray()
            e = bytearray()
            find = 'addEventListener("' + event + '"'
            find1 = 'on' + event
            find2 = 'ga('
            find3 = 'logEvent'
            b.extend(map(ord, find))
            c.extend(map(ord, find1))
            d.extend(map(ord, find2))
            e.extend(map(ord, find3))
            try:
                org_point = s.find(b)
                org_point1 = s.find(c)
                org_point2 = s.find(d)
                org_point3 = s.find(e)
            except OverflowError as err:
                print("File too large")
            if org_point != -1:
                org_point = f.seek(org_point + len(find))
                f.read(1)
                a = f.tell()
                if f.read(1) != " ":
                    f.seek(a)
                a = f.tell()
                if f.read(1) != "(":
                    f.seek(a)
                name = ""
                if f.read(len("function(")) == "function(":
                    point = f.tell()
                    pos = find_end(javascript_file, f.tell(), '{', '}')
                    done = done or ret_post(javascript_file, point, pos)
                else:
                    f.seek(org_point)
                    f.read(1)
                    curr = f.read(1)
                    while curr != "," and curr != '(' and curr != ";":
                        if curr == '.':
                            name = ""
                        elif curr != ' ':
                            name += curr
                        curr = f.read(1)
                    if "fireAnalytics" in name:
                        return True, 0
                    b = bytearray()
                    find = "function " + name
                    b.extend(map(ord, find))
                    try:
                        point = s.rfind(b)
                    except OverflowError as err:
                        print("File too large")
                    if point != -1:
                        point = f.seek(point + len(find))
                        pos = find_end(javascript_file, point, "{", "}")
                        f.seek(pos)
                        done = done or ret_post(javascript_file,point,pos)
            if not done and org_point1 != -1:
                org_point1 = f.seek(org_point1 + len(find1))
                if f.read(1) != " ":
                    f.seek(org_point1)
                aux = f.read(1)
                if aux == "=":
                    pos_aux = f.tell()
                    if f.read(1) != " ":
                        f.seek(pos_aux)
                    a = f.tell()
                    if f.read(1) != "(":
                        f.seek(a)
                    if f.read(len("function(")) == "function(":
                        pos = find_end(javascript_file, pos_aux, "{", "}")
                        done = done or ret_post(javascript_file, pos_aux, pos)
                    else:
                        f.seek(pos_aux)
                        if f.read(1) == "\"":
                            while f.read(1) != "\"":
                                nothing = 0
                            pos = f.tell()
                            done = done or ret_post(javascript_file, pos_aux, pos)
                        else:
                            f.seek(pos_aux)
                            curr = f.read(1)
                            name = curr
                            while curr != "," and curr != '(' and curr != ";":
                                if curr == '.':
                                    name = ""
                                elif curr != ' ':
                                    name += curr
                                curr = f.read(1)
                            c = bytearray()
                            find1 = "function " + name
                            c.extend(map(ord, find))
                            try:
                                point = s.rfind(c)
                            except OverflowError as err:
                                print("File too large")
                            if point != -1:
                                point = f.seek(point + len(find))
                                pos = find_end(javascript_file, point, "{", "}")
                                done = done or ret_post(javascript_file, point, pos)
                elif aux == "(":
                    pos = find_end(javascript_file, org_point1, "{", "}")
                    done = done or ret_post(javascript_file, org_point1, pos)
            if not done and org_point2 != -1:
                point = f.seek(org_point2 + len(find2)-1)
                pos = find_end(javascript_file, point, "(", ")")
                f.seek(pos)
                d = bytearray()
                d.extend(map(ord, event))
                try:
                    ret = s.find(d, point, pos)
                except OverflowError as err:
                    print("File too large")
                if ret != -1:
                    return True
                d = bytearray()
                d.extend(map(ord, 'on' + event))
                try:
                    ret = s.find(d, point, pos)
                except OverflowError as err:
                    print("File too large")
                if ret != -1:
                    return True
            if not done and org_point3 != -1:
                point = f.seek(org_point2 + len(find3))
                pos = find_end(javascript_file, point, "(", ")")
                f.seek(pos)
                d = bytearray()
                d.extend(map(ord, event))
                try:
                    ret = s.find(d, point, pos)
                except OverflowError as err:
                    print("File too large")
                if ret != -1:
                    return True


def get_mouse_fingerprinting(url):
    # Get url info
    db = url.db

    # Get tracking info
    tracking = Connector(db, "tracking")
    if not tracking.load(hash_string("Mouse fingerprinting")):
        tracking.save()

    # Check if already in database
    url_tracking = 0
    if url.get("tracking", {"tracking_id": tracking.values["id"]}):
        url_tracking = 1

    # If not in database compare to mouse tracking domains
    if not url_tracking:
        mouse_tracking_domains = Connector(db, "mouse_tracking_domains")
        mouse_tracking_domains.get_all()
        for domain in mouse_tracking_domains:
            if re.search(domain, url.values["url"]):
                url.add(tracking, {"update_timestamp": utc_now()})
                url_tracking = 1

    # Finish if resource does not exist
    if not url.values["resource_id"]:
        return url_tracking, 0

    # Finish if we don't have the resource in the DB (we only save HTML and JS files)
    resource = Connector(db, "resource")
    resource.load(url.values["resource_id"])
    if not resource.values["file"]:
        return url_tracking, 0

    # Return DB value if already computed
    tracking_list = resource.get("tracking", order="tracking_id")
    for tr in tracking_list:
        if tr.values["id"] == tracking.values["id"]:
            return url_tracking, 1

    # Otherwise extract file and compute
    resource_tracking = 0
    code = zlib.decompress(resource.values["file"])
    tmp_filename = os.path.join(os.path.abspath("."), "tmp", url.values["hash"] + ".js")
    with open(tmp_filename, "wb") as js_file:
        js_file.write(code)
    try:
        tracker = parse_mouse_fingerprinting(tmp_filename)
    except UnicodeDecodeError as e:
        # Probably not an UTF-8 file
        pass
    except Exception as e:
        logger.info("Mouse tracking error %s" % str(e))
    else:
        if tracker:
            resource.add(tracking)
            resource_tracking = 1
    os.remove(tmp_filename)
    return url_tracking, resource_tracking


def check_tracking(url, domain):
    """ Checks all the tracking possible for the given url and domain. """
    #print("Entro HTTP cookies")
    get_http_cookies(url, domain)
    #print("Entro JS cookies")
    get_js_cookies(url)
    #print("Entro font")
    get_font_fingerprinting(url)
    #print("Entro canvas")
    get_canvas_fingerprinting(url)
    #get_mouse_fingerprinting(url)


argument_parser = argparse.ArgumentParser(description='Tracking parser')
argument_parser.add_argument('domains', metavar='N', type=str, nargs='+',
                             help='Domain list to search for tracking info')

if __name__ == '__main__':
    """ Main process """

    # Take arguments
    args = argument_parser.parse_args()
    database = Db()
    for domain_name in args.domains:
        root_domain = Connector(database, "domain")
        if isinstance(domain_name, int):
            root_domain.load(int(domain_name))
        else:
            root_domain.load(hash_string(root_domain))
        url_list = root_domain.get("url", order="url_id")
        for target_url in url_list:
            url_cookies = get_http_cookies(target_url, root_domain)
            num_js_cookies = get_js_cookies(target_url)
            big, small = get_canvas_fingerprinting(target_url)
            url_mouse, resource_mouse = get_mouse_fingerprinting(target_url)
