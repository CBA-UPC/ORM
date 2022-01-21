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

current_timestamp = datetime.now(timezone(timedelta(hours=2), name="UTC+2"))


def parse_cookies(cookie_string):
    """ Parses all the cookies of the given 'set-cookie' string """

    cookie_list = []
    allowed_values = ["expires", "max-age", "domain", "path", "samesite", "secure", "httponly"]
    cookie_lines = cookie_string.split("\n")
    for cookie_line in cookie_lines:
        cookie_line = cookie_line.replace("; ", ";")
        cookie_line = cookie_line.replace(";\";", ";")
        parameters = cookie_line.split(";")
        cookie_created = False
        for parameter in parameters:
            # Avoid empty parameters fix ('set-cookie' strings finished in ';')
            if len(parameter) == 0:
                continue
            parameter_list = parameter.split("=", maxsplit=1)
            if len(parameter_list) == 1:
                parameter_list = parameter.split(":", maxsplit=1)
            key = parameter_list[0].lower()
            key = key.strip()
            if key not in allowed_values:
                # If it is not one of the default values is a new cookie
                if len(parameter_list) == 1:
                    cookie_list.append({"name": parameter_list[0], "value": None})
                else:
                    cookie_list.append({"name": parameter_list[0], "value": parameter_list[1]})
                
                cookie_created = True
            elif key == "expires":
                
                # Create 'datetime' object from expire value
                if parameter_list[1] == "session" or parameter_list[1] == "Session":    
                    cookie_list[-1][key] = datetime.now(timezone(timedelta(hours=2), "UTC+2"))
                elif parameter_list[1].isnumeric():
                    continue
                else:
                    end = parameter_list[1].find("GMT")
                    if end == -1:
                        try:
                            cookie_list[-1][key] = parser.parse(parameter_list[1]+" GMT")
                        except:
                            continue

                    else:
                        try:
                            cookie_list[-1][key] = parser.parse(parameter_list[1][:end+3])
                        except:
                            continue

            elif key == "max-age":
                # Compute expire 'datetime' object from current time + max-age value
                now = datetime.now(timezone(timedelta(hours=2), "UTC+2"))
                if int(parameter_list[1]) >= 31536000*5:
                    cookie_list[-1][key] = now + timedelta(seconds=315360000)
                else:
                    cookie_list[-1][key] = now + timedelta(seconds=int(parameter_list[1]))
            else:
                # For the rest of the allowed values we save them unmodified
                for value in allowed_values:
                    if key == value:
                        if not cookie_created:
                            if len(parameter_list) == 1:
                                cookie_list.append({"name": parameter_list[0], "value": None})
                            else:
                                cookie_list.append({"name": parameter_list[0], "value": parameter_list[1]})
                            cookie_created = True
                        elif key in ["secure", "httponly"]:
                            cookie_list[-1][key] = True
                        else:
                            if len(parameter_list) == 1 or parameter_list[1] == "none" or parameter_list[1] == "None":
                                cookie_list[-1][value] = "None"
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
    now = datetime.now(timezone(timedelta(hours=2), name="UTC+2"))
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
            if cookie[expire_value] > three_months and is_third_party:
                cookie["tracking"] = "Tracking cookies"
            elif is_third_party:
                cookie["tracking"] = "Third-party cookies"
            elif cookie[expire_value] > one_year:
                cookie["tracking"] = "Very long-living cookies"
            elif cookie[expire_value] > three_months and not is_third_party:
                cookie["tracking"] = "Long-living cookies"
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
        url.add(tracking, {"quantity": tracking_list[tracking_value], "update_timestamp": datetime.now(timezone(timedelta(hours=2), name="UTC+2"))})
    
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
            request = "SELECT quantity FROM resource_tracking WHERE resource_id = %d AND tracking_id = %d" % (resource.values["id"], tracking.values["id"])
            return db.custom(request)[0]["quantity"]

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
        url.add(tracking, {"quantity": cookies, "update_timestamp": datetime.now(timezone(timedelta(hours=2), name="UTC+2"))})
        resource.add(tracking, {"quantity": cookies, "update_timestamp": datetime.now(timezone(timedelta(hours=2), name="UTC+2"))})
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
            request = "SELECT quantity FROM resource_tracking WHERE resource_id = %d AND tracking_id = %d" % (resource.values["id"], tracking.values["id"])
            return db.custom(request)[0]["quantity"]

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
        url.add(tracking, {"quantity": file_fonts, "update_timestamp": datetime.now(timezone(timedelta(hours=2), name="UTC+2"))})
        resource.add(tracking, {"quantity": file_fonts, "update_timestamp": datetime.now(timezone(timedelta(hours=2), name="UTC+2"))})
    return file_fonts


def check_canvas_properties(code, prop_1, prop_2, prop_3):
    """ Searches for canvas fingerprint patterns based on given properties inside the given code"""

    # Initialize counting variables
    big = 0
    icon = 0
    small = 0

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
                last_value = ""
                if index < len(piece):
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
            if value == "":
                continue
            if int(value) >= 32:
                big += 1
            elif int(value) >= 16:
                icon += 1
            else:
                small += 1
    return big, icon, small


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
    big_width, icon_width, small_width = check_canvas_properties(code, ".createElement(\"canvas\")", ".width=", ".toDataURL(")
    big_height, icon_height, small_height = check_canvas_properties(code, ".createElement(\"canvas\")", ".height=", ".toDataURL(")
    big_width2, icon_width2, small_width2 = check_canvas_properties(code, ".createElement(\"canvas\")", "width:", ".toDataURL(")
    big_height2, icon_height2, small_height2 = check_canvas_properties(code, ".createElement(\"canvas\")", "height:", ".toDataURL(")
    canvas1 = min(big_width, big_height) + min(big_width2, big_height2)
    canvas2 = min(icon_width, icon_height) + min(icon_width2, icon_height2)

    # If tracking found, save inside DB
    if canvas1:
        resource.add(tracking_big, {"quantity": canvas1, "update_timestamp": datetime.now(timezone(timedelta(hours=2), name="UTC+2"))})
        url.add(tracking_big, {"quantity": canvas1, "update_timestamp": datetime.now(timezone(timedelta(hours=2), name="UTC+2"))})
    if canvas2:
        resource.add(tracking_small, {"quantity": canvas2, "update_timestamp": datetime.now(timezone(timedelta(hours=2), name="UTC+2"))})
        url.add(tracking_small, {"quantity": canvas2, "update_timestamp": datetime.now(timezone(timedelta(hours=2), name="UTC+2"))})
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
            elif curr == end_label or len(curr) < 1:
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
                logger.info("File too large")


def parse_mouse_fingerprinting(javascript_file):
    done = False
    with open(javascript_file) as f:
        try:
            html = f.read(len("<!DOCTYPE html>"))
            f.seek(0)
            if "<!" in html or "docty" in html:
                return False
        except UnicodeDecodeError as e:
            logger.info("Probably not an UTF-8 file")
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
                logger.info("File too large")
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
                        logger.info("File too large")
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
                                logger.info("File too large")
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
                    logger.info("File too large")
                if ret != -1:
                    return True
                d = bytearray()
                d.extend(map(ord, 'on' + event))
                try:
                    ret = s.find(d, point, pos)
                except OverflowError as err:
                    logger.info("File too large")
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
                    logger.info("File too large")
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
    trackings = url.get("tracking", order="tracking_id")

    for t in trackings:
        
        if t.values["id"] == tracking.values["id"]:
            url_tracking = 1
    """if url.get("tracking", {"tracking_id": tracking.values["id"]}):
        url_tracking = 1"""

    # If not in database compare to mouse tracking domains
    if not url_tracking:
        mouse_tracking_domains = Connector(db, "mouse_tracking_domains")
        mouse_tracking_domains = mouse_tracking_domains.get_all()
        for domain in mouse_tracking_domains:
            if re.search(domain, url.values["url"]):
                url.add(tracking, {"update_timestamp": datetime.now(timezone(timedelta(hours=2), name="UTC+2"))})
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
            #resource.add(tracking)
            resource_tracking = 1
            resource.add(tracking, {"quantity": resource_tracking, "update_timestamp": datetime.now(timezone(timedelta(hours=2), name="UTC+2"))})
            url.add(tracking, {"quantity": resource_tracking, "update_timestamp": datetime.now(timezone(timedelta(hours=2), name="UTC+2"))})
    os.remove(tmp_filename)
    return url_tracking, resource_tracking

def get_webgl_fingerprint(url):
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
    tracking.load(hash_string("WebGL fingerprinting"))


    # Return DB value if already computed
    tracking_list = resource.get("tracking", order="tracking_id")
    for tr in tracking_list:
        if tr.values["id"] == tracking.values["id"]:
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
    big_width, icon_width, small_width = check_canvas_properties(code, ".createElement(\"canvas\")", ".width=", ".toDataURL(")
    big_height, icon_height, small_height = check_canvas_properties(code, ".createElement(\"canvas\")", ".height=", ".toDataURL(")
    big_width2, icon_width2, small_width2 = check_canvas_properties(code, ".createElement(\"canvas\")", "width:", ".toDataURL(")
    big_height2, icon_height2, small_height2 = check_canvas_properties(code, ".createElement(\"canvas\")", "height:", ".toDataURL(")

    lista = ["copyBufferSubData","getBufferSubData","blitFramebuffer","framebufferTextureLayer","getInternalformatParameter","invalidateFramebuffer","invalidateSubFramebuffer","readBuffer","renderbufferStorageMultisample","texStorage2D","texStorage3D","texImage3D","texSubImage3D","copyTexSubImage3D","compressedTexImage3D","compressedTexSubImage3D","getFragDataLocation","uniform1ui","uniform2ui","uniform3ui","uniform4ui","uniform1uiv","uniform2uiv","uniform3uiv","uniform4uiv","uniformMatrix2x3fv","uniformMatrix3x2fv","uniformMatrix2x4fv","uniformMatrix4x2fv","uniformMatrix3x4fv","uniformMatrix4x3fv","vertexAttribI4i","vertexAttribI4iv","vertexAttribI4ui","vertexAttribI4uiv","vertexAttribIPointer","vertexAttribDivisor","drawArraysInstanced","drawElementsInstanced","drawRangeElements","drawBuffers","clearBufferiv","clearBufferuiv","clearBufferfv","clearBufferfi","createQuery","deleteQuery","isQuery","beginQuery","endQuery","getQuery","getQueryParameter","createSampler","deleteSampler","isSampler","bindSampler","samplerParameteri","samplerParameterf","getSamplerParameter","fenceSync","isSync","deleteSync","clientWaitSync","waitSync","getSyncParameter","createTransformFeedback","deleteTransformFeedback","isTransformFeedback","bindTransformFeedback","beginTransformFeedback","endTransformFeedback","transformFeedbackVaryings","getTransformFeedbackVarying","pauseTransformFeedback","resumeTransformFeedback","bindBufferBase","bindBufferRange","getIndexedParameter","getUniformIndices","getActiveUniforms","getUniformBlockIndex","getActiveUniformBlockParameter","getActiveUniformBlockName","uniformBlockBinding","createVertexArray","deleteVertexArray","isVertexArray","bindVertexArray"]
    performance = unmasked = res_num_webgl_calls = 0
    
    if code.find(".performance") != -1:
        performance+= 1
    if code.find(".mozPerformance") != -1:
        performance+= 1
    if code.find(".msPerformance") != -1:
        performance+= 1
    if code.find("UNMASKED_RENDERER_WEBGL") != -1:
        unmasked +=1 
    if code.find("UNMASKED_VENDOR_WEBGL") != -1:
        unmasked +=1

    for l in lista:
        if code.find(l) != -1:

            res_num_webgl_calls += 1

    small_canvas = min(small_width, small_height) + min(small_width2, small_height2)
    total = 0
    if small_canvas and (res_num_webgl_calls > 60 or performance > 0 or unmasked > 0):
        
        if res_num_webgl_calls > 60:
            total += 1
        if performance > 0:
            total += 1
        if unmasked > 0:
            total += 1

        resource.add(tracking, {"quantity": total, "update_timestamp": datetime.now(timezone(timedelta(hours=2), name="UTC+2"))})
        url.add(tracking, {"quantity": total, "update_timestamp": datetime.now(timezone(timedelta(hours=2), name="UTC+2"))})
    return total


def check_tracking(url, domain):
    """ Checks all the possible tracking for the given url and domain. """
    get_http_cookies(url, domain)
    get_js_cookies(url)
    get_font_fingerprinting(url)
    get_canvas_fingerprinting(url)
    get_mouse_fingerprinting(url)
    get_webgl_fingerprint(url)

def calculate_intrusion_level(domain):
    intrusion_level = 0
    trackings_in_domain = {}
    urls = domain.get("url", order="url_id")
    
    for url in urls:
        
        trackings = url.get("tracking", order="tracking_id")
        for track in trackings:
            
            if track.values["name"] in trackings_in_domain.keys():
                trackings_in_domain[track.values["name"]] += track.values["intrusion_level"]
            else:
                trackings_in_domain[track.values["name"]] = track.values["intrusion_level"]
    for t in trackings_in_domain:
        
        if trackings_in_domain[t] > 9:
            intrusion_level += 9
        else:
            intrusion_level += trackings_in_domain[t]

    return intrusion_level

def main(process):
    """ Main process in charge of taking work from the queue and extracting info if needed.

    While there is remaining work in the queue continuously passes new jobs until its empty.
    If the 'no-update' argument is false it cleans the previously URL's linked for the current domain. """

    # Load the DB manager for this process
    db = Db()

    while True:
        try:
            queue_lock.acquire()
            site = work_queue.get(False)
            queue_lock.release()
        except queue.Empty:
            queue_lock.release()
            exit(0)
        except Exception as e:
            logger.error("[Worker %d] %s" % (process, str(e)))
        else:
            domain = Connector(db, "domain")
            domain.load(site)
            setproctitle("ORM - Worker #%d - %s" % (process, domain.values["name"]))
            logger.info('[Worker %d] Domain %s' % (process, domain.values["name"]))
            url_list = domain.get("url", order="url_id")
            for url in url_list:
                check_tracking(url, domain)

argument_parser = argparse.ArgumentParser(description='Tracking parser')
argument_parser.add_argument('-t', dest='threads', type=int, default=0,
                    help='Number of threads/processes to span (Default: Auto)')
argument_parser.add_argument('-start', dest='current', type=int, default=0,
                    help='Id for the starting domain (Default: 0).')

if __name__ == '__main__':
    """ Main process """

    # Take arguments
    args = argument_parser.parse_args()
    threads = args.threads
    # If thread parameter is auto get the (total-1) or the available CPU's, whichever is smaller
    logger.info("Calculating processes...")
    if not threads:
        cpu = cpu_count()
        try:
            available_cpu = len(os.sched_getaffinity(0))
        except Exception as e:
            logger.warning("Platform not recognized. Getting the maximum CPU's")
            available_cpu = cpu
        # Save 1 CPU for other purposes
        if cpu > 1 and cpu == available_cpu:
            threads = cpu - 1
        else:
            threads = available_cpu
    logger.info("Processes to run: %d " % threads)
    # Initialize job queue
    work_queue = Queue()
    queue_lock = Lock()

    # Create and call the workers
    logger.debug("[Main process] Spawning new workers...")
    with Pool(processes=threads) as pool:
        p = pool.map_async(main, [i for i in range(int(threads))])

        pending = ["0"]
        current = int(args.current)
        while True:
            # Insert new work into queue if needed.
            queue_lock.acquire()
            qsize = work_queue.qsize()
            queue_lock.release()
            if qsize < (2 * threads):
                logger.debug("[Main process] Getting work")
                now = datetime.now(timezone.utc)
                td = timedelta(-1 * update_threshold)
                period = now + td
                rq = 'SELECT id FROM domain'
                if args.priority:
                    rq += ' WHERE id > %d' % current
                rq += ' AND id NOT IN (%s)' % ','.join(pending)
                rq += ' ORDER BY id ASC LIMIT %d ' % (2 * threads)
                pending = ["0"]
                database = Db()
                results = database.custom(rq)
                database.close()
                # If no new work wait ten seconds and retry
                if len(results) > 0:
                    # Initialize job queue
                    logger.debug("[Main process] Enqueuing work")
                    queue_lock.acquire()
                    for result in results:
                        work_queue.put(result["id"])
                        pending.append(str(result["id"]))
                        current = result["id"]
                    queue_lock.release()
            time.sleep(1)
