import urlparse
import httplib
import subprocess
import libxml2
import os
import logging

def generate_full_auto_path(relative):
    # all of the automated installation paths are installed to $pkg_path/auto,
    # so we just need to find it and generate the right path here
    pkg_path = os.path.dirname(__file__)
    return os.path.abspath(os.path.join(pkg_path, "auto", relative))

# FIXME: we should probably have a maximum number of redirects, to avoid
# possible infinite loops
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
    if response.status == 302:
        redirecturl = response.getheader('location')
        if redirecturl is None:
            raise Exception, "Could not access install url: " + response.reason
        return check_url(redirecturl)
    elif response.status != 200:
        raise Exception, "Could not access install url: " + response.reason
    return url
