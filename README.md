# QoE version of Online Resource Mapper (ORM)
Simplified version of ORM to perform QoE experiments using different browser plugins.

## Setup
### Requirements
We strongly recommend the use of Python 3.7, since lower versions may not support the required modules.
The following packages are required:
* beautifulsoup4 >= 4.8.2
* jsbeautifier >= 1.11.0
* lxml >= 4.5.0
* mysqlclient >= 1.4.6
* requests >= 2.23.0
* selenium == 3.141.0
* tldextract >= 2.2.2

You can install them using *pip*.

We need also the LTS version of node.js to run Google's LightHouse. Depending on the platform the installation procedure differs so we recommend to look for specific instructions for your OS. Once you have it run "npm install -g lighthouse" to install it.

Regarding the browser, we need a Chromium instance with support for the DevTools Protocol. For compatibility reasons we include the deb packages used to perform the experiments in [assets/chromium](assets/chromium). For tracking detection we include 3 different plugins: [AdBlock Plus](https://adblockplus.org), [Ghostery](https://www.ghostery.com/) and [uBlock Origin](https://chrome.google.com/webstore/detail/ublock-origin/cjpalhdlnbpafiamejdnhcphjbkeiagm?hl=es). Inside [assets/plugins](assets/plugins) there are the versions used for our experiments although ORM should be compatible with newer versions. 


Lastly, we will make use of [Mysql Workbench](https://www.mysql.com/products/workbench/) to create and maintain the database used to store the information. The database was created with MySQL 5.7.30.

### Installation
1) Load the database structure included inside [assets/database](assets/database) with MySQL Workbench, then synchronize the model with the server where the data is going to be stored. The default database name is ORM. To force script compatibility with MySQL 5.7.30, specify "5.7.30" as the "Target MySQL Version" inside "Model Options" of MySQL Workbench.

2) Modify the DB connection information accordingly inside [config.py](config.py).

3) Execute [db_initializer.py](code/db_initializer.py) to store the basic data inside the database.

Usage: db_initializer.py 0 1000

The two parameters specify the range of the most popular websites to include inside the database. 
To explore more parameters execute "db_initializer --help".

4) Execute [ORM-QoE.py](code/ORM-QoE.py) to start parsing websites.

Usage: ORM-QoE.py -start 0 -end 1000 -t 4

The third parameter tells ORM how many threads to use to parse websites. 

## Things to note

* Each ORM thread opens a number of browser instances equivalent to the number of content-blocker plugins we configure plus one more for the vanilla browser. By default four plugins are opened (3 adblockers + 1 vanilla browser) so each thread will open four browsers to compare the resources obtained by each of them. Be careful launching large amounts of threads as each browser instance can consume a considerable amount of memory.

* Each website is loaded 5 times consecutively to be able to compare them and avoid temporal conditions such as rush hours, network problems or periodic maintenances.

* The URL information is stored inside the "url" table. Each table including two nouns joined by an underscore (e.g. "domain_url") states the relation between the two. Accessing the data by means of specific scripts will give the user access to all the information available inside the database.

## Authors
* Ismael Castell-Uroz
* Pere Barlet-Ros
