# Online Resource Mapper (ORM)
ORM is a mapper tool created with the objective of mapping the relation between each URL with the resources loaded when opening it. The tool makes use of a customized version of uBlock Origin to list and automatically label all the resources loaded by the inspected websites. The obtained information can be used for multiple online studies like finding the most used resources as well as the number of websites loading a specific resource.

We found that only one instance of the system can scrape information from thousands of different websites in a single day, but nothing impedes launching it in a clustering configuration. Using it we were able to collect a complete dataset of the resource information (files, script, documents, etc.) of the top 1,000,000 most popular websites per the Tranco list. The collection process took less than one month to finish and includes information about more than 75 million of different resources. During our experiments we have applied the datasets obtained to discover new web tracking detection methods, as well as to develop a privacy obserbatory called [ePrivo](https://eprivo.eu). In case of interest, please contact us at "contact"at"eprivo.eu".

## Setup
### Requirements
We strongly recommend the use of at least Python 3.7, since lower versions may not support the required modules. The framework was developed under Ubuntu 18.04 LTS and there may be some incompatibilities with newer versions of some of the libraries and modules, especially with Selenium. In the [assets/firefox](assets/firefox) directory there is also included the firefox and geckodriver versions used during the development for compatibility reasons. Newer versions may introduce changes that render the framework useless. We are currently working on updating the code to support newer versions of all the tools used.

The following packages are required:
* wheel>=0.36.2
* beautifulsoup4>=4.8.2
* geoip2>=3.0.0
* jsbeautifier>=1.11.0
* lxml>=4.5.0
* mysqlclient>=1.4.6
* pyrabin>=0.6
* requests>=2.23.0
* selenium==3.141.0
* tldextract>=2.2.2
* asn1crypto>=1.4.0
* esprima>=4.0.1
* python-dateutil>=2.8.1
* setproctitle>=1.2.2
* urllib3==1.26.6

You can install them using *pip install -r requirements.txt* from the downloaded folder. To compile some of the modules you will need the python-dev library corresponding to you Python version.

Moreover, to compute the *fuzzy_hashes* used to compare resources, we need to install tlsh. You can follow the official [guide.](https://github.com/trendmicro/tlsh) For future proof, we include inside [assets](assets/) folder the current version of the module used by ORM.

The system automatically labels all the URLs/resources as if would have been blocked by uBlock Origin, one of the most famous and complete content-blockers on the market. To do so we instrumented uBlock Origin (v1.32.5) to allow all the URLs without blocking them but labeling them in the process. The customized version of uBlock Origin is included in [custom_ublock_origin](assets/plugin/custom_ublock_origin). 

Lastly, we will make use of [Mysql Workbench](https://www.mysql.com/products/workbench/) to create and maintain the database used to store the information. The database model has to be configured as at least MySQL 5.7.8. for compatibility with JSON fields, used to save multiple information about the headers and certificates.

### Installation
1) Load the database structure included inside [assets/database](assets/database) with MySQL Workbench, then synchronize the model with the server where the data is going to be stored. The default database name is ORM. To force script compatibility with MySQL 5.8.7, specify "5.8.7" as the "Target MySQL Version" inside "Model Options" of MySQL Workbench.

2) rename the [config_example.py](code/config_example.py) to config.py and modify the DB connection information inside according to your database parameters.

3) Create a "log" folder inside the "code" folder.

4) Execute [db_initializer.py](code/db_initializer.py) to store the basic data inside the database. By default it stores the top 1M most popular websites currently listed in the [Tranco list](https://tranco-list.eu/) but this range can be selected with the "-start" and "-end" parameters. Alternatively, you can select a csv file with domain information (1 domain per line) to insert inside the database.

* Usage: db_initializer.py -start 1 -end 1000000

5) Execute [ORM.py](code/ORM.py) to start parsing websites. Parameters "-start" and "-end" can be used to define the range of websites to scrape. The parameter "-t" tells ORM how many threads should be instantiated to parse websites. 

* Usage: orm.py -start 1 -end 1000 -t 4

## Things to note
Each ORM thread opens a browser with the customized uBlock Origin plugin. Needless to say a, a full-fledged browser consumes a portion of your CPU and memory resources. Consequently, be careful launching large amounts of threads as each browser instance can consume a considerable amount of memory.

The resource information is stored inside the "resource" table. In the same way, the URLs and domains are stored inside their own tables. Each table including two nouns joined by an underscore (e.g. "domain_url") states the relation between the two. Accessing the data by means of specific scripts will give the user access to all the information available inside the database.

## Publications
ORM and its collected datasets had been the base for multiple scientific publications. You can find here a list of some of them.

* I. Castell-Uroz, J. Solé-Pareta and P. Barlet-Ros, ["Network Measurements for Web Tracking Analysis and Detection: A Tutorial,"](https://upcommons.upc.edu/handle/2117/335316) in IEEE Instrumentation & Measurement Magazine, vol. 23, no. 9, pp. 50-57, December 2020, doi: 10.1109/MIM.2020.9289071.

* I. Castell-Uroz, J. Solé-Pareta and P. Barlet-Ros, ["Demystifying Content-blockers: A Large-scale Study of Actual Performance Gains,"](https://upcommons.upc.edu/handle/2117/335314) 2020 16th International Conference on Network and Service Management (CNSM), Izmir, Turkey, 2020, pp. 1-7, doi: 10.23919/CNSM50824.2020.9269094.

* I. Castell-Uroz, T. Poissonnier, P. Manneback and P. Barlet-Ros, ["URL-based Web Tracking Detection Using Deep Learning,"](https://upcommons.upc.edu/handle/2117/334688) 2020 16th International Conference on Network and Service Management (CNSM), Izmir, Turkey, 2020, pp. 1-5, doi: 10.23919/CNSM50824.2020.9269065.

* I. Castell-Uroz, J. Solé-Pareta and P. Barlet-Ros, ["TrackSign: Guided web tracking discovery,"](https://upcommons.upc.edu/handle/2117/351439/) IEEE INFOCOM 2021-IEEE Conference on Computer Communications, Vancouver, BC, Canada, 2021, pp. 1-10, doi: 10.1109/INFOCOM42981.2021.9488842.

* I. Castell-Uroz, K. Fukuda and P. Barlet-Ros, ["ASTrack: Automatic Detection and Removal of Web Tracking Code with Minimal Functionality Loss,"](https://arxiv.org/pdf/2301.10895) IEEE INFOCOM 2023-IEEE Conference on Computer Communications, New York, United States, 2023, pp. 1-10, doi: 10.1109/INFOCOM53939.2023.10228902.

* I. Castell-Uroz, I. Douha-Prieto, M. Basart-Dotras, P. Mesegue-Molina and P. Barlet-Ros, ["ePrivo. eu: An Online Service for Automatic Web Tracking Discovery,"](https://ieeexplore.ieee.org/abstract/document/10050035) IEEE ACCESS, 2023, pp. 1-11, doi: 10.1109/ACCESS.2023.3247863.

## Authors
* Ismael Castell-Uroz
* Pere Barlet-Ros
