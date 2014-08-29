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

CSV File format example:<br/>
[1] ip,label<br/>
    202.13.234.12,Server A<br/>
    212.50.177.10,Server B<br/>
    ...<br/>

[2] label,desc,ip<br/>
    Server A,This is Server 1,202.13.234.12<br/>
    Server B,This is Server 2,212.50.177.10<br/>
    ...<br/>

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
