import sys
import zlib
import csv
import time
import os
import datetime
import json
from datetime import timedelta

#Mouse Tracking
import mmap
import re

from db_manager import Db, Connector
from utils import hash_string, utc_now
db = Db()


if len(sys.argv) != 2:
  print("Usage: $ python3 tracker_detector.py <url> ")
  exit()

url = sys.argv[1]

#PRE: url_id is the id of the url and tracking_name is the name of the tracking techinque
def add_relation_url_tracking(url_id, tracking_name):
  
  url = Connector(db, "url")
  url.load(url_id)
  tracking = Connector(db, "tracking")
  tracking.load(hash_string(tracking_name))
  timestamp = datetime.datetime.utcnow() + timedelta(seconds=7200)
  url.add(tracking, {"update_timestamp": timestamp})
  
  
#PRE: resource_id is the id of the resource and tracking_name is the name of the tracking techinque
def add_relation_resource_tracking(resource_id, tracking_name):
  
  resource = Connector(db, "resource")
  resource.load(resource_id)
  tracking = Connector(db, "tracking")
  tracking.load(hash_string(tracking_name))
  timestamp = datetime.datetime.utcnow() + timedelta(seconds=7200)
  resource.add(tracking, {"update_timestamp": timestamp})

# Converts the first three letters of a month to its number
def edit_month(month):
  
  if month == "Jan":
    return 1
  elif month == "Feb":
    return 2
  elif month == "Mar":
    return 3
  elif month == "Apr" or month == "04":
    return 4
  elif month == "May":
    return 5
  elif month == "Jun":
    return 6
  elif month == "Jul":
    return 7
  elif month == "Aug":
    return 8
  elif month == "Sep":
    return 9
  elif month == "Oct":
    return 10
  elif month == "Nov":
    return 11
  elif month == "Dec":
    return 12

def init_all_result():
  result = {}

  domains = Connector(db, "domain") #Connector
  domains = domains.get_all({})
  for domain in domains:
    
    result[str(domain.values["name"])] = {"cookies": {"header": 0, "js": 0}, "canvas": {".width=": 0, ".height=": 0, "width:": 0, "height:": 0}, "font": {"num_fonts": 0, ".offsetHeight": 0, ".offsetWidth": 0}, "mouse": 0, "webgl": {"calls": 0, "performance": 0, "unmasked": 0}}
  
  return result

def init_result(url):
  result = {}
  result[str(url)] = {"cookies": {"header": 0, "js": 0}, "canvas": {".width=": 0, ".height=": 0, "width:": 0, "height:": 0}, "font": {"num_fonts": 0, ".offsetHeight": 0, ".offsetWidth": 0}, "mouse": 0, "webgl": {"calls": 0, "performance": 0, "unmasked": 0}}
  return result



def header_cookies(urls):

  for key in urls:
    """print("DOMAIN -> " + key)
    print("------------------------------------")"""
    domain = Connector(db, "domain") #Connector
    domain.load(hash_string(key))
    urls_query = domain.get("url", order="url_id")
    #num_cookies = ""
    
    three_months = datetime.datetime(2021, 6, 6)
    one_year = datetime.datetime(2022, 4, 6)
    for url in urls_query:
      req_h = url.values["request_headers"]
      res_h = url.values["response_headers"]
      url_id = url.values["id"]
    
      if res_h is not None and (res_h.find("set-cookie") != -1 or res_h.find("Set-Cookie") != -1):
       
        num_cookies_res = len(res_h.split("set-cookie"))-1 + len(res_h.split("Set-Cookie"))-1
        #num_cookies = str(res_h.split("set-cookie")) + str(res_h.split("set-cookie"))
        #print("#Cookies -> " + str(num_cookies_res) + " URL -> " + str(url.values["id"]) + " ")

        json_res = json.loads(res_h)


        start_search = 0
        for i in range(num_cookies_res):

          if str(json_res).find("expires=", start_search) != -1 or str(json_res).find("Expires=", start_search) != -1:
            
            ini = str(json_res).find("Expires=")
            if ini == "-1":
              ini = str(json_res).find("expires=")

            end = str(json_res).find(";", ini)
            exp = str(json_res)[ini+8:end]
            pos_GMT = exp.find("GMT")
            
            if pos_GMT == -1:
              #Forever?
              continue
            else:
              pos_coma = exp.find(",")
              exp = exp[pos_coma+2:pos_GMT-10]
              
              if exp.find(" ") != -1:
                exp_splitted = exp.split(" ")
              else:
                exp_splitted = exp.split("-")
              
              day = exp_splitted[-3]
              month = exp_splitted[-2]
              year = exp_splitted[-1]
              int_year = 0
              
              if not year.isnumeric():
                int_year = int(year[-4:])
                #print("YEAR -> " + str(int_year))
              else:
                int_year = int(year)
              if int_year < 100:
                if int_year < 70:
                  int_year += 2000
                else:
                  int_year += 1900
                year = str(int_year)
              
              int_month = edit_month(month)
              
              
              #print(datetime.datetime(int(year), int_month, int(day)))
              try:
                int_year = int(year)
                int_day = int(day)
                date = datetime.datetime(int_year, int_month, int_day)
                is_third_party = False

                ini_dom = str(json_res).find("Domain=")
                if ini_dom == -1:
                  ini_dom = str(json_res).find("domain=")
                if ini_dom != -1:

                  end_dom = str(json_res).find(";", ini_dom)
                  dom = str(json_res)[ini_dom+7:end_dom]
                  #print("DOMAIN -> " + dom)
                  if dom.find(key) == -1:
                    is_third_party = True
                else:
                  #Check URL domain
                  #Acabar de determinar si es ThirdP o FirstP
                  #print("No domain specified")
                  if json_res.get("Host") is not None and json_res.get("Host").find(key) == -1:
                    is_third_party = True
                  

                if (one_year < date) or (three_months < date and is_third_party):
                  
                  #print("Permanent cookie -> RED " + day + " " + month + " " + year )

                  #add_relation_resource_tracking(res_id,"Cookies ORANGE")
                  add_relation_url_tracking(url_id,"Cookies RED")
                elif (three_months < date and not is_third_party) or (is_third_party):
                  #print("Permanent cookie -> ORANGE " + day + " " + month + " " + year )
                  add_relation_url_tracking(url_id,"Cookies ORANGE")
                elif not is_third_party:
                  #print("Permanent cookie -> GREEN " + day + " " + month + " " + year )
                  add_relation_url_tracking(url_id,"Cookies GREEN")


              except :
                  print("COOKIE: Bad format")
          else:
            null = 0
            #print("Session cookie -> GREEN")
          start_search = end
        
            
        
    
    urls[key]["cookies"]["header"] = num_cookies_res
    #print("------------------------------------")
    
    

  return urls
    
  
def js_cookies(urls):

  for key in urls:

    domain = Connector(db, "domain") #Connector
    domain.load(hash_string(key))
    urls_query = domain.get("url", order="url_id")
    num_cookies = 0
    for url in urls_query:
      res_id = url.values["resource_id"]

      if res_id is not None:
        resource = Connector(db, "resource")
        resource.load(res_id)
        js_compressed = resource.values["file"]
        
        if js_compressed is not None:
          js_obfuscated = zlib.decompress(js_compressed)
            
          try:
            result_query = str(js_obfuscated,'utf-8')
          except:
            result_query = str(js_obfuscated)
          #js_clean = jsbeautifier.beautify(js_obfuscated)
          
          
          if result_query.find(".cookie=") != -1:
  
            num_cookies += len(result_query.split(".cookie="))-1
            
    urls[key]["cookies"]["js"] = num_cookies
    
  return urls



def html_canvas(urls):

  for key in urls:

    domain = Connector(db, "domain") #Connector
    domain.load(hash_string(key))
    urls_query = domain.get("url", order="url_id")
    num_canvas = 0
    for url in urls_query:
      res_id = url.values["resource_id"]
      url_id = url.values["id"]

      if res_id is not None:
        resource = Connector(db, "resource")
        resource.load(res_id)
        js_compressed = resource.values["file"]
        
        if js_compressed is not None:
          js_obfuscated = zlib.decompress(js_compressed)
            
          try:
            html = str(js_obfuscated,'utf-8')
          except:
            html = str(js_obfuscated)
          #js_clean = jsbeautifier.beautify(js_obfuscated)
          
          icon_size = False
          big_size = False

          html = html[:-1]
          html = html.replace("b'", "")
          html = html.replace("\\\\", "")
          html = html.replace("\\n", "")
          html = html.replace("\\'", "'")
          if html.find(".createElement(\"canvas\")") != -1 and html.find(".width=") != -1 and html.find(".toDataURL(") != -1:
            
            num_splits = len(html.split(".width="))
            ini = 0
            for n in range(num_splits-1):

              ind = html.find(".width=",ini+1) + len(".width=")
              still = True
              value = ""
              while still:
                
                last_value = html[ind:ind+1]
                if last_value.isnumeric():
                  value += html[ind:ind+1]
                  ind += 1
                elif last_value == "\"":
                  ind += 1
                else:
                  if len(value) != 0 and last_value != "%":
                    int_value = int(value)                      
                    
                    
                    if int_value >= 16:
                      urls[key]["canvas"][".width="] += 1
                      if int_value > 32:
                        big_size = True
                      else:
                        icon_size = True
                      
        
                  still = False
              
              ini = ind

          if html.find(".createElement(\"canvas\")") != -1 and html.find(".height=") != -1 and html.find(".toDataURL(") != -1:
            
            num_splits = len(html.split(".height="))
            ini = 0
            for n in range(num_splits-1):
              
              ind = html.find(".height=",ini+1) + len(".height=")
              still = True
              value = ""
              while still:
                
                last_value = html[ind:ind+1]
                if last_value.isnumeric():
                  value += html[ind:ind+1]
                  ind += 1
                elif last_value == "\"":
                  ind += 1
                else:
                  if len(value) != 0 and last_value != "%":
                    int_value = int(value)
                    
                    if int_value >= 16:

                      urls[key]["canvas"][".height="]+= 1

                      if int_value > 32 and big_size:
                        #Guardo como red
                        add_relation_resource_tracking(res_id,"Canvas fingerprinting RED")
                        add_relation_url_tracking(url_id,"Canvas fingerprinting RED")
                      if int_value <= 32 and icon_size:
                        #Guardo como orange
                        add_relation_resource_tracking(res_id,"Canvas fingerprinting ORANGE")
                        add_relation_url_tracking(url_id,"Canvas fingerprinting ORANGE")
        
                  still = False
              
              ini = ind

          icon_size = False
          big_size = False

          if html.find(".createElement(\"canvas\")") != -1 and html.find("width:") != -1 and html[html.find("width:")-1] != "-" and html.find(".toDataURL(") != -1:
            
            num_splits = len(html.split("width:"))
            ini = 0
            for n in range(num_splits-1):
              
              ind = html.find("width:",ini+1) + len("width:")
              still = True

              if html[html.find("width:",ini+1)-1] == "-":
                still = False

              value = ""
              while still:
                
                last_value = html[ind:ind+1]
                if last_value.isnumeric():
                  value += html[ind:ind+1]
                  ind += 1
                elif last_value == "\"":
                  ind += 1
                else:
                  if len(value) != 0 and last_value != "%":
                    int_value = int(value)
                    
                    if int_value >= 16:

                      urls[key]["canvas"]["width:"]+= 1
                      if int_value > 32:
                        big_size = True
                      else:
                        icon_size = True
        
                  still = False
              
              ini = ind

          if html.find(".createElement(\"canvas\")") != -1 and html.find("height:") != -1 and html.find(".toDataURL(") != -1:
            
            num_splits = len(html.split("height:"))
            ini = 0
            for n in range(num_splits-1):
              
              ind = html.find("height:",ini+1) + len("height:")
              still = True

              if html[html.find("height:",ini+1)-1] == "-":
                still = False
              
              value = ""
              while still:
                
                last_value = html[ind:ind+1]
                if last_value.isnumeric():
                  value += html[ind:ind+1]
                  ind += 1
                elif last_value == "\"":
                  ind += 1
                else:
                  if len(value) != 0 and last_value != "%":
                    int_value = int(value)
                    
                    if int_value >= 16:

                      urls[key]["canvas"]["height:"]+= 1

                      if int_value > 32 and big_size:
                        #Guardo como red
                        add_relation_resource_tracking(res_id,"Canvas fingerprinting RED")
                        add_relation_url_tracking(url_id,"Canvas fingerprinting RED")

                      if int_value <= 32 and icon_size:
                        #Guardo como orange
                        add_relation_resource_tracking(res_id,"Canvas fingerprinting ORANGE")
                        add_relation_url_tracking(url_id,"Canvas fingerprinting ORANGE")


                  still = False
              
              ini = ind
            
  return urls


def resource_font(urls):
  f = open("font/fonts.txt", "r")
  fonts = f.read()
  fonts = fonts.split(";")
  num_key = 0
  for key in urls:
    num_key += 1
    #print(num_key)
    domain = Connector(db, "domain")  # Connector
    domain.load(hash_string(key))
    urls_query = domain.get("url", order="url_id")
    

    for url in urls_query:
      
      res_id = url.values["resource_id"]
      url_id = url.values["id"]
      fonts_per_file = 0
      offsetHeight = 0
      offsetWidth = 0

      if res_id is not None:
        resource = Connector(db, "resource")
        resource.load(res_id)
        js_compressed = resource.values["file"]

        if js_compressed is not None:
          js_obfuscated = zlib.decompress(js_compressed)

          try:
            res = str(js_obfuscated, 'utf-8')
          except:
            res = str(js_obfuscated)
          #js_clean = jsbeautifier.beautify(js_obfuscated)

          for font in fonts: 
            if res.find(font) != -1:
              fonts_per_file += 1
            
          if res.find(".offsetHeight") != -1:
            offsetHeight += 1

          if res.find(".offsetWidth") != -1:
            offsetWidth += 1

          if fonts_per_file > urls[key]["font"]["num_fonts"] and offsetHeight >= urls[key]["font"][".offsetHeight"] and offsetWidth >= urls[key]["font"][".offsetWidth"]:

            urls[key]["font"]["num_fonts"] = fonts_per_file
            urls[key]["font"][".offsetHeight"] = offsetHeight
            urls[key]["font"][".offsetWidth"] = offsetWidth
          
          if fonts_per_file >= 29 and offsetHeight > 0 and offsetWidth > 0:
            #print(fonts_per_file)
            add_relation_resource_tracking(res_id,"Font fingerprinting")
            add_relation_url_tracking(url_id,"Font fingerprinting")

  return urls

def find_end(javascript_file, a, ini_label, end_label): #Auxiliar function of mouse tracking
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
            #print(curr)
            if curr == ini_label:
                val += 1
            elif curr == end_label:
                if val == 0:
                    end = True
                    pos = f.tell()
                else:
                    val -= 1
    return pos


def ret_post(javascript_file, ini, end): #Auxiliar function of mouse tracking
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


def scan(javascript_file):  # Main function of mouse tracking
  mouseEvents = ["scroll", "drag", "dragend", "dragstart", "dragleave", "dragover", "drop", 
               "mozInputSource", "buttons", "movementX", "movementY", "mozPressure", "pressure", "deltaX", "deltaY", "deltaZ", "deltaWheel"]
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
  return done

def resource_mouse(urls):
  
  for key in urls:
    print(key)
    domain = Connector(db, "domain") #Connector
    domain.load(hash_string(key))
    urls_query = domain.get("url", order="url_id")
    num_mouse_track = 0
    for url in urls_query:
      res_id = url.values["resource_id"]

      if res_id is not None:
        resource = Connector(db, "resource")
        resource.load(res_id)
        js_compressed = resource.values["file"]
        
        if js_compressed is not None:
          js_obfuscated = zlib.decompress(js_compressed)
            
          try:
            res = str(js_obfuscated,'utf-8')
          except:
            res = str(js_obfuscated)
          #js_clean = jsbeautifier.beautify(js_obfuscated)

          #print(res)
          if len(res) > 0:
            path = "./tmp/res.js"
            tmp_file = open(path, "w")
            tmp_file.write(res)
            tmp_file.close()
            """with open(path) as fichero:
              print(fichero.read())
            
            print("RESOURCE ID -> " + str(res_id))
            print("RESOURCE LENGTH -> " + str(len(res)))"""
            print("RESOURCE ID -> " + str(res_id))
            if scan(path):
              num_mouse_track += 1
            
    urls[key]["mouse"] = num_mouse_track

  return urls



def results_printer(results):
  csv_header = ["domain", "cookies_header", "cookies_js", "canvasFP_js", "canvasFP_html_.width=", "canvasFP_html_.height=", "canvasFP_html_width:", "canvasFP_html_height:", "fonts_per_file", "font_.offsetHeight", "font_.offsetWidth", "mouse", "webgl_calls", "webgl_performance", "webgl_unmasked"]
  with open("tracking_report.csv", 'w', newline='') as csv_file:
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow(csv_header)

    for key, value in results.items():

      csv_writer.writerow([key, value["cookies"]["header"], value["cookies"]["js"],  value["canvas"][".width="], value["canvas"][".height="], value["canvas"]["width:"], value["canvas"]["height:"], value["font"]["num_fonts"], value["font"][".offsetHeight"], value["font"][".offsetWidth"], value["mouse"], value["webgl"]["calls"], value["webgl"]["performance"], value["webgl"]["unmasked"]])
      print(key + " ->", end="")

      tracking = " None"
      if value["cookies"]["header"] > 0 or value["cookies"]["js"] > 0:
        if tracking == " None":
          tracking = " Cookies"
        else:
          tracking += " Cookies"

      if value["canvas"][".width="] > 0 or value["canvas"][".height="] > 0 or value["canvas"]["width:"] > 0 or value["canvas"]["height:"] > 0:
        if tracking == " None":
          tracking = " CanvasFP"
        else:
          tracking += " CanvasFP"
      
      if value["font"]["num_fonts"] >= 29 and value["font"][".offsetHeight"] > 0 and value["font"][".offsetWidth"] > 0:
        if tracking == " None":
          tracking = " Font"
        else:
          tracking += " Font"

      if value["mouse"] > 0:
        if tracking == " None":
          tracking = " Mouse"
        else:
          tracking += " Mouse"
      
      print(tracking)
  
  res_json = json.dumps(results)
  f = open("tracking_report.json", "w")
  f.write(res_json)
  f.close()


      

if url == "all":
  result = init_all_result()
  result = js_cookies(result)
  result = header_cookies(result)
  result = html_canvas(result)
  result = resource_font(result)
  #result = resource_mouse(result)
  results_printer(result)
else:
  result = init_result(url)
  result = js_cookies(result)
  result = header_cookies(result)
  result = html_canvas(result)
  result = resource_font(result)
  #result = resource_mouse(result)
  results_printer(result)