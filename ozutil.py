import urlparse
import httplib

def check_url(url):
    # a basic check to make sure that the url exists
    p = urlparse.urlparse(url)
    if p[0] != "http":
        raise Exception, "Must use http install URLs"
    if p[1] == "localhost" or p[1] == "localhost.localdomain" or p[1] == "127.0.0.1":
        raise Exception, "Can not use localhost for an install URL"
    conn = httplib.HTTPConnection(p[1])
    conn.request("GET", p[2])
    response = conn.getresponse()
    if response.status != 200:
        raise Exception, "Could not access install url: " + response.reason

def check_iso_install(iso):
    print "Checking ISO...",
    check_url(iso)
    print "OK"

def check_url_install(url):
    print "Checking URL...",
    check_url(url)
    print "OK"
