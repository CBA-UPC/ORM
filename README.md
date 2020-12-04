# Online Resource Mapper (ORM)
ORM is a mapper tool created with the objective of mapping the relation between each URL with the resources loaded when opening it. The tool makes use of Google's DevTools protocol included in Chromium to list all the resources loaded by the inspected websites. The obtained information can be used for multiple online studies like finding the most used resources as well as the number of websites loading a specific resource.

ORM also tries to automatically unminify/unobfuscate the code of the resources found to ease their study if necessary. During our experiments we found that only one instance of the system can scrap information from thousands of different websites in a single day, but nothing impedes launching it in a clustering configuration. Using it we were able to collect a complete dataset of the resource information (files, script, documents, etc.) of the top 100.000 most popular websites per the Alexa list. The collection process took 7 days to finish and includes information about approximately 20 million of different resources, representing more than 250GB of data. In case of interest, please contact UPC at "icastell"at"ac.upc.edu". Moreover, the "data" folder contains a dataset collected using ORM about the performance using different content-blockers to browse the top 100K most popular websites.

## Setup
### Requirements
We strongly recommend the use of Python 3.7, since lower versions may not support the required modules.
The following packages are required:
* beautifulsoup4 >= 4.8.2
* geoip2 == 3.0.0
* jsbeautifier >= 1.11.0
* lxml >= 4.5.0
* mysqlclient >= 1.4.6
* pyrabin == 0.6
* requests >= 2.23.0
* selenium == 3.141.0
* tldextract >= 2.2.2

You can install them using *pip*.

Moreover, to compute the *fuzzy_hashes* used to compare resources, we need to install tlsh. You can follow the official [guide.](https://github.com/trendmicro/tlsh) For future proof, we include inside [assets](assets/) folder the current version of the module used by ORM.

We also need the "abpy" module to compare the collected URLs with the tracking patterns found in [EasyList](https://easylist.to/easylist/easylist.txt), [EasyPrivacy](https://easylist.to/easylist/easyprivacy.txt) or other similar pattern lists.
For compatibility reasons we include inside the code folder the module used by ORM.

Regarding the browser, we need a Chromium instance with support for the DevTools Protocol. For compatibility reasons we include the deb packages used to develop the tool in [assets/chromium](assets/chromium). For tracking detection we include 3 different plugins: [AdBlock Plus](https://adblockplus.org), [Ghostery](https://www.ghostery.com/) and [uBlock Origin](https://chrome.google.com/webstore/detail/ublock-origin/cjpalhdlnbpafiamejdnhcphjbkeiagm?hl=es). Inside [assets/plugins](assets/plugins) there are the versions used for our experiments although ORM should be compatible with newer versions. 


Lastly, we will make use of [Mysql Workbench](https://www.mysql.com/products/workbench/) to create and maintain the database used to store the information.

### Installation
1) Load the database structure included inside [assets/database](assets/database) with MySQL Workbench, then synchronize the model with the server where the data is going to be stored. The default database name is ORM.

2) Modify the DB connection information accordingly inside [config.py](config.py).

3) Execute [db_initializer.py](code/db_initializer.py) to store the basic data inside the database.

Usage: db_initializer.py 0 1000

The two parameters specify the range of the most popular websites to include inside the database. 
To explore more parameters execute "db_initializer --help".

4) Execute [orm.py](code/orm.py) to start parsing websites.

Usage: orm.py -start 0 -end 1000 -t 4

The third parameter tells ORM how many threads to use to parse websites. 

5) To initially label the resources as tracking or not, we can execute [code/labeler.py](code/labeler.py). It will label them as per the pattern lists included inside the [assets/pattern](assets/pattern) folder.

## Things to note

* Each ORM thread opens a number of browser instances equivalent to the number of content-blocker plugins we configure plus one more for the vanilla browser. By default only uBlock Origin is configured so each thread will open two browsers to compare the resources gotten by a clean browser and a protected one. Be careful launching large ammounts of threads as each browser instance can consume a considerable amount of memory.

* The resource information is stored inside the "resource" table. In the same way, the URLs, domains and code fingerprints are stored inside their own tables. Each table including two nouns joined by an underscore (e.g. "domain_url") states the relation between the two. Accessing the data by means of specific scripts will give the user access to all the information available inside the database.

* The [fingerprinter.py](code/fingerprinter.py) script partitions the downloaded code in unambiguous pieces.

## Authors
* Ismael Castell-Uroz
* Pere Barlet-Ros
