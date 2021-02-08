# Online Resource Mapper (ORM)
ORM is a mapper tool created with the objective of mapping the relation between each URL with the resources loaded when opening it. The tool makes use of Google's DevTools protocol included in Chromium to list all the resources loaded by the inspected websites. The obtained information can be used for multiple online studies like finding the most used resources as well as the number of websites loading a specific resource.

During our experiments we found that only one instance of the system can scrap information from thousands of different websites in a single day, but nothing impedes launching it in a clustering configuration. Using it we were able to collect a complete dataset of the resource information (files, script, documents, etc.) of the top 100.000 most popular websites per the Alexa list. The collection process took 7 days to finish and includes information about approximately 20 million of different resources, representing more than 250GB of data. In case of interest, please contact UPC at "icastell"at"ac.upc.edu". Moreover, the "data" folder contains a dataset collected using ORM about the performance using different content-blockers to browse the top 100K most popular websites.

## Setup
### Requirements
We strongly recommend the use of Python 3.7, since lower versions may not support the required modules.
The following packages are required:
* beautifulsoup4 >= 4.8.2
* geoip2 >= 3.0.0
* jsbeautifier >= 1.11.0
* lxml >= 4.5.0
* mysqlclient >= 1.4.6
* pyrabin >= 0.6
* requests >= 2.23.0
* selenium >= 3.141.0
* tldextract >= 2.2.2
* asn1crypto >= 1.4.0

You can install them using *pip install -r requirements.txt* from the downloaded folder.

Moreover, to compute the *fuzzy_hashes* used to compare resources, we need to install tlsh. You can follow the official [guide.](https://github.com/trendmicro/tlsh) For future proof, we include inside [assets](assets/) folder the current version of the module used by ORM.

The system automatically labels all the URLs/resources as if would have been blocked by uBlock Origin, one of the most famous and complete content-blockers on the market. To do so we instrumented uBlock Origin (v1.32.5) to allow all the URLs without blocking them but labeling them in the process. The customized version of uBlock Origin is included in [custom_ublock_origin](assets/plugin/custom_ublock_origin). 

Lastly, we will make use of [Mysql Workbench](https://www.mysql.com/products/workbench/) to create and maintain the database used to store the information. The database model has to be configured as at least MySQL 5.7.8. for compatibility with JSON fields, used to save multiple information about the headers and certificates.

### Installation
1) Load the database structure included inside [assets/database](assets/database) with MySQL Workbench, then synchronize the model with the server where the data is going to be stored. The default database name is ORM. To force script compatibility with MySQL 5.8.7, specify "5.8.7" as the "Target MySQL Version" inside "Model Options" of MySQL Workbench.

2) Modify the DB connection information accordingly inside [config.py](code/config.py).

3) Execute [update_top1M.sh](assets/alexa/update_top1M.sh) to download the most recent version of Alexa's top 1M popular website list.

4) Create a "log" folder inside the "code" folder.

5) Execute [db_initializer.py](code/db_initializer.py) to store the basic data inside the database.
Usage: db_initializer.py 0 1000

The two parameters specify the range of the most popular websites to include inside the database. 
To explore more parameters execute "db_initializer --help".

6) Execute [orm.py](code/ORM.py) to start parsing websites.

Usage: orm.py -start 0 -end 1000 -t 4

The third parameter tells ORM how many threads to use to parse websites. 

## Things to note

* Each ORM thread opens a browser with the customized uBlock Origin plugin. Needless to say a, a full-fledged browser consumes a portion of your CPU and memory resources. Consequently, be careful launching large amounts of threads as each browser instance can consume a considerable amount of memory.

* The resource information is stored inside the "resource" table. In the same way, the URLs, domains and code fingerprints are stored inside their own tables. Each table including two nouns joined by an underscore (e.g. "domain_url") states the relation between the two. Accessing the data by means of specific scripts will give the user access to all the information available inside the database.

* The [fingerprinter.py](code/fingerprinter.py) script partitions the downloaded code in unambiguous pieces using Rabin fingerprinting over the file code.

## Publications
ORM and its collected datasets had been the base for multiple scientific publications. You can find here a list of some of them.

* I. Castell-Uroz, J. Solé-Pareta and P. Barlet-Ros, ["Network Measurements for Web Tracking Analysis and Detection: A Tutorial,"](https://upcommons.upc.edu/handle/2117/335316) in IEEE Instrumentation & Measurement Magazine, vol. 23, no. 9, pp. 50-57, December 2020, doi: 10.1109/MIM.2020.9289071.

* I. Castell-Uroz, J. Solé-Pareta and P. Barlet-Ros, ["Demystifying Content-blockers: A Large-scale Study of Actual Performance Gains,"](https://upcommons.upc.edu/handle/2117/335314) 2020 16th International Conference on Network and Service Management (CNSM), Izmir, Turkey, 2020, pp. 1-7, doi: 10.23919/CNSM50824.2020.9269094.

* I. Castell-Uroz, T. Poissonnier, P. Manneback and P. Barlet-Ros, ["URL-based Web Tracking Detection Using Deep Learning,"](https://upcommons.upc.edu/handle/2117/334688) 2020 16th International Conference on Network and Service Management (CNSM), Izmir, Turkey, 2020, pp. 1-5, doi: 10.23919/CNSM50824.2020.9269065.

## Authors
* Ismael Castell-Uroz
* Pere Barlet-Ros
