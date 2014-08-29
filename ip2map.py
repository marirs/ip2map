#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Description:
    Take input of multiple ip addresses from a file and pass it to telize api to
    determine the details of the IP, like ASN,ISP,LATITUDE,LONGITUDE, etc.
    There is a default column of 12 columns of descriptions. If the csv file, contins other columns
    along with IP address, then those columns also gets appended to the default

    Once we determine the above information of the IP, we will use amcharts/amMaps to create
    a bubble/heat map in PNG format

Requirements:
    1) requests (pip install requests OR sudo easy_install requests)

    2) PhantomJS (if you desire to convert the resulting html to SVG/PNG/PDF)
        for Mac: brew update && brew install phantomjs
        for Windows: https://bitbucket.org/ariya/phantomjs/downloads/phantomjs-1.9.7-windows.zip
        for Linux: sudo yum install fontconfig freetype libfreetype.so.6 libfontconfig.so.1 libstdc++.so.6
                and then download: https://bitbucket.org/ariya/phantomjs/downloads/phantomjs-1.9.7-linux-x86_64.tar.bz2
                        or 32bit: https://bitbucket.org/ariya/phantomjs/downloads/phantomjs-1.9.7-linux-i686.tar.bz2

    3) AmMaps - provided by http://www.amcharts.com/javascript-maps/
        They have both free and paid versions, choose which one you want. The script very well works on free version
        We just need the ammaps.js, ammaps.css and the worldHigh.svg

Usage:
    ip2map.py <ip_address|file> [options]

    Options:
      --version             show program's version number and exit
      -h, --help            show this help message and exit
      -q, --quiet           execute the program silently
      --heading=HEADING     Heading for the Map
      -l <col_name>, --label=<col_name>
                            column name from generated data to label the bubbles,
                            eg: -l col10
      --sub-heading=SUB HEADING
                            Sub Heading for the Map
      -u UA, --ua=UA        define a specific user agent you choose to use

CSV File format example:
[1] ip,label
    202.13.234.12,Server A
    212.50.177.10,Server B
    ...

[2] label,desc,ip
    Server A,This is Server 1,202.13.234.12
    Server B,This is Server 2,212.50.177.10
    ...

Examples:
    $ ./ip2map.py ips.txt --heading "World wide connections" --sub-heading "-- month: jul2014 --"
        generates a world map with the heading and sub heading shown above
        generates both heat-map and bubbles

    $ ./ip2map.py ips.txt --heading "" --sub-heading "" -l col4
        generates a world map with no heading and sub heading
        generates both heat map and bubbles. The bubbles will have labels from col4 (country)

    $ ./ip2map.py ips.txt --heading "" --sub-heading "" -l col13
        gets the labels from col13. In this case, col13 will be an extra column that is read from a file.
        There are only 12 columns, if its just IP address in the CSV.
"""
from optparse import OptionParser
from operator import itemgetter
import os, sys, socket, logging, re, csv
import requests, json, subprocess, datetime

__author__ = 'Sriram G'
__version__ = '1'
__license__ = 'GPLv3'

"""
Global variables
"""
UA = "Mozilla/5.0 (Windows NT 6.3; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/37.0.2049.0 Safari/537.36"
quiet_mode = False
logger = logging.getLogger('ip2map')
logger.setLevel(logging.DEBUG)
logging.basicConfig(format='[%(levelname)-7s] %(asctime)s | %(message)s', datefmt='%I:%M:%S %p') #%m/%d/%Y


def uniq(_1colList):
    """
    Uniquify a list that has a single column
    returns: list of unique col (as a list)
    """
    return [l for i,l in enumerate(_1colList) if l not in _1colList[i+1:]]


def uniq_list(list_dict, key):
    """
    pass a list of dictionaries and the key you want to unique the list
    returns: a list of dictionaries that are unique based on the key column passed
    """
    seen = set()
    seen_add = seen.add
    return [x for x in list_dict if x[key] not in seen and not seen_add(x[key])]


def is_valid_ip(ip):
    """
    validates the given IP addresses
    ip v4 or ipv6 can be passed
    returns: True if IP detected or False (bool)
    """
    def is_valid_ipv4(ip):
        """
        validates IPv4 addresses.
        """
        pattern = re.compile(r"""
            ^
            (?:
              # Dotted variants:
              (?:
                # Decimal 1-255 (no leading 0's)
                [3-9]\d?|2(?:5[0-5]|[0-4]?\d)?|1\d{0,2}
              |
                0x0*[0-9a-f]{1,2}  # Hexadecimal 0x0 - 0xFF (possible leading 0's)
              |
                0+[1-3]?[0-7]{0,2} # Octal 0 - 0377 (possible leading 0's)
              )
              (?:                  # Repeat 0-3 times, separated by a dot
                \.
                (?:
                  [3-9]\d?|2(?:5[0-5]|[0-4]?\d)?|1\d{0,2}
                |
                  0x0*[0-9a-f]{1,2}
                |
                  0+[1-3]?[0-7]{0,2}
                )
              ){0,3}
            |
              0x0*[0-9a-f]{1,8}    # Hexadecimal notation, 0x0 - 0xffffffff
            |
              0+[0-3]?[0-7]{0,10}  # Octal notation, 0 - 037777777777
            |
              # Decimal notation, 1-4294967295:
              429496729[0-5]|42949672[0-8]\d|4294967[01]\d\d|429496[0-6]\d{3}|
              42949[0-5]\d{4}|4294[0-8]\d{5}|429[0-3]\d{6}|42[0-8]\d{7}|
              4[01]\d{8}|[1-3]\d{0,9}|[4-9]\d{0,8}
            )
            $
        """, re.VERBOSE | re.IGNORECASE)
        return pattern.match(ip) is not None


    def is_valid_ipv6(ip):
        """
        validates IPv6 addresses.
        """
        pattern = re.compile(r"""
            ^
            \s*                         # Leading whitespace
            (?!.*::.*::)                # Only a single wildcard allowed
            (?:(?!:)|:(?=:))            # Colon if it would be part of a wildcard
            (?:                         # Repeat 6 times:
                [0-9a-f]{0,4}           #   A group of at most four hexadecimal digits
                (?:(?<=::)|(?<!::):)    #   Colon unless preceded by wildcard
            ){6}                        #
            (?:                         # Either
                [0-9a-f]{0,4}           #   Another group
                (?:(?<=::)|(?<!::):)    #   Colon unless preceded by wildcard
                [0-9a-f]{0,4}           #   Last group
                (?: (?<=::)             #   Colon iff preceded by exactly one colon
                 |  (?<!:)              #
                 |  (?<=:) (?<!::) :    #
                 )                      # OR
             |                          #   A v4 address with NO leading zeros
                (?:25[0-4]|2[0-4]\d|1\d\d|[1-9]?\d)
                (?: \.
                    (?:25[0-4]|2[0-4]\d|1\d\d|[1-9]?\d)
                ){3}
            )
            \s*                         # Trailing whitespace
            $
        """, re.VERBOSE | re.IGNORECASE | re.DOTALL)
        return pattern.match(ip) is not None


    return is_valid_ipv4(ip) or is_valid_ipv6(ip)


def ip2loc(ip_list=[]):
    """
    accepts a single ip or list of ip's as a list
    and get the extra information of the ip address from telize.com api
    returns: details of the ip with 12 columns (as a list)
    """
    logger.debug("ip2loc().ip2map.py...starts getting ip info for %s ips"%str(len(ip_list)))
    api_url = "http://www.telize.com/geoip/%s"

    headers = {'User-Agent': UA}
    ip2loc_list = []
    for ip in ip_list:
        """ip, country_code, country_code3, country, region_code, region, city,
	    postal_code, continent_code, latitude, longitude, dma_code, area_code, asn, isp, timezone
        """
        try:
            response = requests.get(api_url % ip, headers=headers)
            json_data = json.loads(response.text)
        except ValueError:
            break

        try: country_code2= json.dumps(json_data["country_code"]).replace('"',"").strip()
        except KeyError: country_code2= 'N/A'
        try: country_code3= json.dumps(json_data["country_code3"]).replace('"',"").strip()
        except KeyError: country_code3= 'N/A'
        try: country= json.dumps(json_data["country"]).replace('"',"").strip()
        except KeyError: country= 'N/A'
        try: city= json.dumps(json_data["city"]).replace('"',"").strip()
        except KeyError: city= 'N/A'
        try: region= json.dumps(json_data["region"]).replace('"',"").strip()
        except KeyError: region= 'N/A'
        try: region_code= json.dumps(json_data["region_code"]).replace('"',"").strip()
        except KeyError: region_code= 'N/A'
        try: lat= json.dumps(json_data["latitude"]).replace('"',"").strip()
        except KeyError: lat= 'N/A'
        try: lng= json.dumps(json_data["longitude"]).replace('"',"").strip()
        except KeyError: lng= 'N/A'
        try: zip= json.dumps(json_data["postal_code"]).replace('"',"").strip()
        except KeyError: zip= 'N/A'
        try: isp= json.dumps(json_data["isp"]).replace('"',"").strip()
        except KeyError: isp= 'N/A'
        try: asn= json.dumps(json_data["asn"]).replace('"',"").strip()
        except KeyError: asn= 'N/A'

        t = [ip, lat, lng, country_code2, country_code3, country, region_code, region,city, zip, asn, isp]
        ip2loc_list.append(t)
    logger.debug("ip2loc().ip2map.py...finished")
    """
    returns:
    ipaddress, latitude, longitude, country_code2, country_code3, country, region_code, region, city, postal_code, asn, isp
    """
    return ip2loc_list

def print_csv(csv_content, csv_mode=True):
    """
    Prints CSV file to standard output.
    If csv_mode is set to false, prints a tab separated output
    returns: none
    """
    if not csv_mode:
        print(120*'-')
        for row in csv_content:
            row = [str(e) for e in row]
            print('\t'.join(row))
        print(120*'-')
    else:
        print(120*'-')
        pCSV = csv.writer(sys.stdout)
        [pCSV.writerow(row) for row in csv_content]
        print(120*'-')


def read_csv_file(fn):
    """
    read the given file:
    the given input file MUST have a header
    returns: headers (as list), number of columns (as int), data (as list of dictionaries)
    """
    logger.debug("Reading from file %s" % fn)
    infile = fn
    infile = open(infile, "rU")
    reader = csv.reader(infile)
    headers = reader.next()
    num_columns = len(headers)

    # Read the column names from the first line of the file
    csv_lst = []
    for row in reader:
        items = dict(zip(headers, row))
        csv_lst.append(items)

    return headers, num_columns, csv_lst


def file_name(fn):
    """
    check to see if given file exists, if it does, return
    incremented file name
    returns: as file name format (as string)
    """
    _of = ""
    files = [f for f in os.listdir(".") if re.match(fn,f)]
    if files:
        _of = fn + "_%02d" % (len(files)+1)
    else:
        _of = fn + "_01"

    return _of

def touchCSV(fn, csvList, append=False):
    """
    function to write a list as csv to a file
    returns: none
    """
    mode = ("a+b" if append else "wb")
    with open(fn, mode) as f:
        writer = csv.writer(f)
        writer.writerows(csvList)


def touch(fn, contents, append=False):
    """
    generic function to write to a file with
    given contents
    returns: none
    """
    mode = ("a" if append else "w")
    f = open(fn, mode)
    f.write(contents)
    f.close()

def rm(fn):
    """
    generic function to remove a file
    returns: none
    """
    os.remove(fn)

def main():
    """
    main function
    """
    all_ips = []
    processed = []
    final_processed = []
    parser = OptionParser()
    mapHeading = ""
    mapSubHeading = ""
    label = ""
    label_col = 9
    cols = 0
    data = 0
    ip_col_idx=0
    ip_col_key = 0
    found_ip_header = False
    new_csv_header = []
    csvHeader = ['ipaddress', 'latitude', 'longitude', 'country_code2', 'country_code3', 'country', 'region_code', 'region', 'city', 'postal_code', 'asn', 'isp']
    file_format = datetime.date.today().strftime("%Y%m%d")
    parser = OptionParser(usage="usage: %prog <ip_address|file> [options] ", version="%prog v1")
    parser.add_option("-q","--quiet",action="store_true",dest="quiet_mode",help="execute the program silently",default=False)
    parser.add_option("--heading", dest="mapHeading",help="Heading for the Map", metavar="HEADING",default="HEAT MAP")
    parser.add_option("-l","--label", dest="label",help="column name from generated data to label the bubbles, eg: -l col10", metavar="<col_name>",default="")
    parser.add_option("--sub-heading", dest="mapSubHeading",help="Sub Heading for the Map", metavar="SUB HEADING",default="-- locations this month --")
    parser.add_option("-u","--ua", dest="UA",help="define a specific user agent you want to use", metavar="UA",default="Mozilla/5.0 (Windows NT 6.3; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/37.0.2049.0 Safari/537.36")

    (options, args) = parser.parse_args()
    quiet_mode = options.quiet_mode
    mapHeading = options.mapHeading
    mapSubHeading = options.mapSubHeading
    label = options.label
    UA = options.UA
    if quiet_mode: logger.setLevel(logging.INFO)

    # check to see if we got a IP Address or a File with batch ip's
    if len(args) == 1:
        #1 argument found, check to see if its a IP address
        try:
            socket.inet_aton(args[0])
            all_ips.append(args[0])
        except socket.error:
            # not a ip address, but check to see if its a valid file
            if os.path.isfile(args[0]):
                # Read from File (mostly batch)
                logger.debug("Loading file...")
                # read the ip addresses
                header, cols, data = read_csv_file(args[0])
                """
                get the index of "ip address" field
                also get the key name @ index
                """
                ip_col_idx = 0
                found_ip_header = False
                for h in header:
                    if 'ip' in str(h).lower():
                        found_ip_header = True
                        break
                    ip_col_idx += 1
                if not found_ip_header:
                    logger.error("Did not find a header label with 'ip' or 'ip address', etc. Make sure, your file has a header and IP column has label that starts with 'ip'")
                    sys.exit(1)

                ip_col_key = header[ip_col_idx] # get the column name as in csv file
                logger.debug("ip address column @ col%d:'%s'" % (ip_col_idx, ip_col_key))
                data = uniq_list(data, ip_col_key) # make this list of dicts unique based on IP addresses

                # get the ip's from list
                for i in data:
                    if is_valid_ip(i[ip_col_key]):
                        all_ips.append(i[ip_col_key])
                    else:
                        logger.error("%s not a valid ip address, ignoring this ip..." % i[ip_col_key])
                # Got all the ip's from the file
                logger.debug("Total unique ip's to process: %s" % str(len(all_ips)))
            else:
                print "%s is not valid..." % args[0]
                parser.print_help()
                sys.exit(0)
    else:
        print "No valid ip address or file provided"
        parser.print_help()
        sys.exit(0)

    """
    confirm if the ammap.js, ammap.css, worldHigh.svg are present
    to generate the map
    """
    # ammap.js
    if not os.path.isfile("ammap.js"):
        logger.error("ammap.js not available, cannot generate map.")
        sys.exit(1)

    # ammap.css
    if not os.path.isfile("ammap.css"):
        logger.error("ammap.css not available, cannot generate map.")
        sys.exit(1)

    # worldHigh.svg
    if not os.path.isfile("worldHigh.svg"):
        logger.error("worldHigh.svg not available, cannot generate map.")
        sys.exit(1)

    logger.info("Gathering ip\'s information...")
    processed += ip2loc(all_ips)

    """
    add the new columns to the corresponding ip's from the dict
    which was taken from the file
    """
    final_processed.append(csvHeader)   # add the csv header
    if cols > 1:
        for ip in processed:
            found = filter(lambda x: x[ip_col_key] == ip[0], data)
            tmp=[]
            for dicts in found:
                for k,v in dicts.iteritems():
                    if k not in ip_col_key:
                        tmp.append(v)
                        # append csv_headers
                        if k not in new_csv_header: new_csv_header.append(k)
                final_processed.append(ip + tmp)
        final_processed[0] += new_csv_header # add the new csv header
    else:
        final_processed += processed

    del processed   # free processed
    del data        # free data

    logger.debug("New headers found: %s" % new_csv_header)
    """
    understand the bubble labels
    if user has passed a column number to print as label on map, check and add it
    """
    if label=="":
        label_col = 9
        label = "//label:dataItem.name"
    else:
        label_col = int(re.findall(r'\d+',label)[0])
        if label_col > len(csvHeader):
            logger.error("Label is using invalid col #: %s. There are only %d columns. Labels are disabled" % (label,len(csvHeader)))
            label_col = 0
            label = "//label:dataItem.name"
        else:
            label = "label:dataItem.name"
            label_col = label_col - 1

    """
    pivot some statistics with the collected results to prepare
    for mapping
    """
    logger.debug("pivoting of data begins...")
    # pivot countries
    countries = [row[3] for row in final_processed[1:]]
    countryStats=[]
    b = {}
    for item in countries:
        b[item] = b.get(item, 0) + 1
    for key, value in b.iteritems():
        temp = [key,value]
        if not key in 'N/A':  countryStats.append(temp)
    countryStats = sorted(countryStats, key=itemgetter(1),reverse=True)
    countryStatsJson = json.dumps([dict(id=cc, value=v) for cc,v in countryStats])
    areas_heatmap = "areas: " + countryStatsJson

    # pivot latitude's
    lats = [row[1] for row in final_processed[1:]]
    latsStats=[]
    b = {}
    for item in lats:
        b[item] = b.get(item, 0) + 1
    for key, value in b.iteritems():
        temp = [key,value]
        if not key in 'N/A':  latsStats.append(temp)
    latsStats =  sorted(latsStats, key=itemgetter(1),reverse=True)

    latlonData = []
    for i in final_processed[1:]:
        if i[3] not in 'N/A':
            latlonData.append("latlong['%s-%s'] = {'latitude':%s, 'longitude':%s};\n" % (i[3], str(i[6]).replace("/",""), i[1], i[2]))

    """
    generate the data for displaying bubbles
    """
    mapData = []
    for i in latsStats:
        found = filter(lambda x:x[1]==i[0],final_processed)
        found = '{"code":"%s-%s" , "name":"%s", "value":%d, "color":"#6c00ff"}' %(found[0][3],str(found[0][6]).replace("/",""),
                                        found[0][label_col],i[1]) # found[0][5] - label col default
        mapData.append(found)


    logger.debug("amMaps generation")
    """
    AmMaps:: begin
    """
    am_maps_html = """
        <html>
        <link rel="stylesheet" href="ammap.css" type="text/css">
        <script src="ammap.js" type="text/javascript"></script>

        <script>

        var map;
        var minBulletSize = 10;
        var maxBulletSize = 40;
        var min = Infinity;
        var max = -Infinity;

        var latlong = {};
        %s

        var mapData = [
        %s
        ]

        // get min and max values
        for (var i = 0; i < mapData.length; i++) {
            var value = mapData[i].value;
            if (value < min) {
                min = value;
            }
            if (value > max) {
                max = value;
            }
        }

        // build map
        AmCharts.ready(
                function() {
                    map = new AmCharts.AmMap();

                    map.addTitle("%s", 20);
                    map.addTitle("%s", 10);
                    map.colorSteps =  3;

                    map.areasSettings = {
                        autoZoom: false,
                        unlistedAreasColor: "#DDDDDD",
                        selectable: false,
                        //unlistedAreasAlpha: 0.1,
                        //rollOverOutlineColor: "#FFFFFF",
                        //selectedColor: "#FFFFFF",
                        //rollOverColor: "#FFFFFF",
                        //outlineAlpha: 0.3,
                        //outlineColor: "#FFFFFF",
                        //outlineThickness: 1,
                        color: "#FFDE00",
                        colorSolid: "#CC9933"
                    };

                    map.imagesSettings = {
                        alpha:0.4,
                        outlineColor: "#CECCCC",
                        outlineThickness: 1
                    }

                    map.zoomControl = {
                        panControlEnabled: false,
                        zoomControlEnabled: false
                    }

                    var dataProvider = {
                        mapURL: "worldHigh.svg",
                        images: [],

                        %s
                    }

                    // create circle for each country
                    for (var i = 0; i < mapData.length; i++) {
                        var dataItem = mapData[i];
                        var value = dataItem.value;
                        // calculate size of a bubble
                        var size = (value - min) / (max - min) * (maxBulletSize - minBulletSize) + minBulletSize;
                        if (size < minBulletSize) {
                            size = minBulletSize;
                        }
                        var id = dataItem.code;

                        dataProvider.images.push({
                            type: "circle",
                            width: size,
                            height: size,
                            color: dataItem.color,
                            longitude: latlong[id].longitude,
                            latitude: latlong[id].latitude,
                            %s,
                            //scale:0.5,
                            //size:8,
                            //labelPosition: "left",
                            //labelShiftX:60, labelShiftY:-12,
                            title: dataItem.name,
                            value: value
                        });
                    }

                    /*map.legend = {
                          width: 150,
                          backgroundAlpha: 0.5,
                          backgroundColor: "#FFFFFF",
                          borderColor: "#666666",
                          borderAlpha: 1,
                          bottom: 15,
                          left: 15,
                          top: 400,
                          horizontalGap: 10,
                          data: [
                          {
                          title: "high",
                          color: "#3366CC"},
                          {
                          title: "moderate",
                          color: "#FFCC33"},
                          {
                          title: "low",
                          color: "#66CC99"}
                          ]
                    };*/

                    map.valueLegend = {
                        right: 10,
                        minValue: "low",
                        maxValue: "high"
                    }

                    map.dataProvider = dataProvider;
                    map.write("mapdiv");

        });

        </script>


        <body>
        <div id="mapdiv" style="width:1200px; height:700px; background-color:#eeeeee;"></div>
        </body>
        </html>
    """
    am_maps_html = am_maps_html % (''.join(latlonData), ','.join(mapData), mapHeading, mapSubHeading, areas_heatmap, label )
    file_format = file_name("%s" % file_format)
    logger.debug(file_format)
    csv_file = "%s_data.CSV" % file_format
    html_file = "%s_html.html" % file_format
    png_file = "%s_map.png" % file_format
    phantom_js = """
        var page = require('webpage').create();
        page.open('%s', function() {
          page.render('%s');
          phantom.exit();
        });
    """ % (html_file,png_file)
    touch(html_file,am_maps_html)
    touch(os.path.join("map.js"),phantom_js)
    touchCSV(csv_file,final_processed)
    touchCSV(csv_file,countryStats,True)
    # bring phantomJS to do the png generation:
    cmd = "phantomjs map.js"
    phantom_process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        output, errors = phantom_process.communicate()
        logger.info("MAP file generated @ %s" % png_file)

    except Exception as e:
        logger.error("Exception: %s" % e)
        logger.error("Map file could not be generated: Mostly no phantomJS")
        phantom_process.kill()

    logger.info("Data file generated @ %s" % csv_file)
    # clean up
    rm("map.js")
    rm(html_file)

    """
    end of main function
    """


if __name__ == '__main__':
    main()



"""
<<< EOF
"""
