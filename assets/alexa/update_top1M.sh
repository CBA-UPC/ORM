#!/bin/sh
# Builds top-1m.csv.zip (the file ALEXA_FILE_PATH points at) from the NetAPI Top 1M.
# The Alexa Top 1M was retired in 2022 and its old S3 address serves a placeholder now;
# the NetAPI Top 1M (https://netapi.com/top-1-mln-websites/, CC BY 4.0) has the same
# rank,domain layout plus one header line, which is dropped here. Requires wget and zip.

wget -O netapi_top1mln.csv https://netapi.com/netapi_top1mln.csv
tail -n +2 netapi_top1mln.csv > top-1m.csv
rm -f netapi_top1mln.csv top-1m.csv.zip
zip top-1m.csv.zip top-1m.csv
rm -f top-1m.csv
