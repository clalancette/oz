import urlparse
import httplib
import subprocess
import libxml2
import os

def generate_full_auto_path(relative):
    # all of the automated installation paths are installed to $pkg_path/auto,
    # so we just need to find it and generate the right path here
    pkg_path = os.path.dirname(__file__)
    print os.path.abspath(os.path.join(pkg_path, "auto", relative))
    return os.path.abspath(os.path.join(pkg_path, "auto", relative))

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

def check_iso_install(iso):
    print "Checking ISO...",
    ret = check_url(iso)
    print "OK"
    return ret

def check_url_install(url):
    print "Checking URL...",
    ret = check_url(url)
    print "OK"
    return ret

def capture_screenshot(xml, filename):
    doc = libxml2.parseMemory(xml, len(xml))
    graphics = doc.xpathEval('/domain/devices/graphics')
    if len(graphics) != 1:
        print "Failed to find port"
        return
    graphics_type = graphics[0].prop('type')
    port = graphics[0].prop('port')

    if graphics_type != 'vnc':
        print "Graphics type is not VNC, not taking screenshot"
        return

    if port is None:
        print "Port is not specified, not taking screenshot"
        return

    vncport = int(port) - 5900

    vnc = "localhost:" + str(vncport)
    ret = subprocess.call(['gvnccapture', vnc, filename], stdout=open('/dev/null', 'w'), stderr=subprocess.STDOUT)
    if ret != 0:
        print "Failed to take screenshot"
