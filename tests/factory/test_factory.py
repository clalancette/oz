#!/usr/bin/python

from __future__ import print_function
import sys
try:
    import configparser
except ImportError:
    import ConfigParser as configparser
try:
    from io import StringIO, BytesIO
except:
    from StringIO import StringIO
    BytesIO = StringIO
import logging
import os

# Find oz library
prefix = '.'
for i in range(0,3):
    if os.path.isdir(os.path.join(prefix, 'oz')):
        sys.path.insert(0, prefix)
        break
    else:
        prefix = '../' + prefix

try:
    import oz.TDL
    import oz.GuestFactory
except ImportError as e:
    print(e)
    print('Unable to import oz.  Is oz installed or in your PYTHONPATH?')
    sys.exit(1)

try:
    import py.test
except ImportError:
    print('Unable to import py.test.  Is py.test installed?')
    sys.exit(1)

# Define a list to collect all tests
alltests = list()

# Define an object to record test results
class TestResult(object):
    def __init__(self, *args, **kwargs):
        if len(args) == 4:
            (self.distro, self.version, self.arch, self.installtype) = args
        for k,v in list(kwargs.items()):
            setattr(self, k, v)

    def __repr__(self):
        '''String representation of object'''
        return "test-{0}-{1}-{2}-{3}".format(*self.test_args())

    @property
    def name(self):
        '''Convenience property for test name'''
        return self.__repr__()

    def test_args(self):
        return (self.distro, self.version, self.arch, self.installtype)

    def execute(self):
        if self.expect_pass:
            return (self.name, runtest, self.test_args())
        else:
            return (self.name, handle_exception, self.test_args())

def default_route():
    route_file = "/proc/net/route"
    d = file(route_file)

    for line in d:
        info = line.split()
        if (len(info) != 11): # 11 = typical num of fields in the file
            logging.warn(_("Invalid line length while parsing %s.") %
                         (route_file))
            break
        try:
            route = int(info[1], 16)
            if route == 0:
                return info[0]
        except ValueError:
            continue
    raise Exception("Could not find default route")

# we find the default route for this machine.  Note that this very well
# may not be a bridge, but for the purposes of testing the factory, it
# doesn't really matter; it just has to have an IP address
route = default_route()

def runtest(args):
    global route

    (distro, version, arch, installtype) = args
    print("Testing %s-%s-%s-%s..." % (distro, version, arch, installtype), end=' ')

    tdlxml = """
<template>
  <name>tester</name>
  <os>
    <name>%s</name>
    <version>%s</version>
    <arch>%s</arch>
    <install type='%s'>
      <%s>http://example.org</%s>
    </install>
    <key>1234</key>
  </os>
</template>
""" % (distro, version, arch, installtype, installtype, installtype)

    tdl = oz.TDL.TDL(tdlxml)

    print(route)
    config = configparser.SafeConfigParser()
    config.readfp(BytesIO("[libvirt]\nuri=qemu:///session\nbridge_name=%s" % route))

    if os.getenv('DEBUG') != None:
        logging.basicConfig(level=logging.DEBUG, format="%(message)s")
    else:
        logging.basicConfig(level=logging.ERROR, format="%(message)s")

    oz.GuestFactory.guest_factory(tdl, config, None)

def expect_success(*args):
    '''Create a TestResult object using provided arguments.  Append result to
    global 'alltests' list.'''
    global alltests
    alltests.append(TestResult(*args, expect_pass=True))

def expect_fail(*args):
    '''Create a TestResult object using provided arguments.  Append result to
    global 'alltests' list.'''
    global alltests
    alltests.append(TestResult(*args, expect_pass=False))

def handle_exception(args):
    '''Helper method to capture OzException when executing 'runtest'.'''
    with py.test.raises(oz.OzException.OzException):
        runtest(args)

def test_all():

    # bad distro
    expect_fail("foo", "1", "i386", "url")
    # bad installtype
    expect_fail("Fedora", "14", "i386", "dong")
    # bad arch
    expect_fail("Fedora", "14", "ia64", "iso")

    # FedoraCore
    for version in ["1", "2", "3", "4", "5", "6"]:
        for arch in ["i386", "x86_64"]:
            for installtype in ["url", "iso"]:
                expect_success("FedoraCore", version, arch, installtype)
    # bad FedoraCore version
    expect_fail("FedoraCore", "24", "x86_64", "iso")

    # Fedora
    for version in ["7", "8", "9", "10", "11", "12", "13", "14", "15", "16",
                    "17", "18", "19"]:
        for arch in ["i386", "x86_64"]:
            for installtype in ["url", "iso"]:
                expect_success("Fedora", version, arch, installtype)
    # bad Fedora version
    expect_fail("Fedora", "24", "x86_64", "iso")

    # RHL
    for version in ["7.0", "7.1", "7.2", "7.3", "8", "9"]:
        expect_success("RHL", version, "i386", "url")
    # bad RHL version
    expect_fail("RHL", "10", "i386", "url")
    # bad RHL arch
    expect_fail("RHL", "9", "x86_64", "url")
    # bad RHL installtype
    expect_fail("RHL", "9", "x86_64", "iso")

    # RHEL-2.1
    for version in ["GOLD", "U2", "U3", "U4", "U5", "U6"]:
        expect_success("RHEL-2.1", version, "i386", "url")
    # bad RHEL-2.1 version
    expect_fail("RHEL-2.1", "U7", "i386", "url")
    # bad RHEL-2.1 arch
    expect_fail("RHEL-2.1", "U6", "x86_64", "url")
    # bad RHEL-2.1 installtype
    expect_fail("RHEL-2.1", "U6", "i386", "iso")

    # RHEL-3/CentOS-3
    for distro in ["RHEL-3", "CentOS-3"]:
        for version in ["GOLD", "U1", "U2", "U3", "U4", "U5", "U6", "U7", "U8",
                        "U9"]:
            for arch in ["i386", "x86_64"]:
                expect_success(distro, version, arch, "url")
    # bad RHEL-3 version
    expect_fail("RHEL-3", "U10", "x86_64", "url")
    # invalid RHEL-3 installtype
    expect_fail("RHEL-3", "U9", "x86_64", "iso")

    # RHEL-4/CentOS-4
    for distro in ["RHEL-4", "CentOS-4", "ScientificLinux-4"]:
        for version in ["GOLD", "U1", "U2", "U3", "U4", "U5", "U6", "U7", "U8",
                        "U9"]:
            for arch in ["i386", "x86_64"]:
                for installtype in ["url", "iso"]:
                    expect_success(distro, version, arch, installtype)
    # bad RHEL-4 version
    expect_fail("RHEL-4", "U10", "x86_64", "url")

    # RHEL-5/CentOS-5
    for distro in ["RHEL-5", "CentOS-5", "ScientificLinux-5"]:
        for version in ["GOLD", "U1", "U2", "U3", "U4", "U5", "U6", "U7", "U8",
                        "U9", "U10"]:
            for arch in ["i386", "x86_64"]:
                for installtype in ["url", "iso"]:
                    expect_success(distro, version, arch, installtype)
    # bad RHEL-5 version
    expect_fail("RHEL-5", "U20", "x86_64", "url")

    # RHEL-6
    for distro in ["RHEL-6", "CentOS-6", "ScientificLinux-6", "OEL-6"]:
        for version in ["0", "1", "2", "3", "4"]:
            for arch in ["i386", "x86_64"]:
                for installtype in ["url", "iso"]:
                    expect_success(distro, version, arch, installtype)
    # bad RHEL-6 version
    expect_fail("RHEL-6", "U10", "x86_64", "url")

    # Debian
    for version in ["5", "6", "7"]:
        for arch in ["i386", "x86_64"]:
            expect_success("Debian", version, arch, "iso")
    # bad Debian version
    expect_fail("Debian", "12", "i386", "iso")
    # invalid Debian installtype
    expect_fail("Debian", "6", "x86_64", "url")

    # Windows
    expect_success("Windows", "2000", "i386", "iso")
    for version in ["XP", "2003", "2008", "7", "8", "2012"]:
        for arch in ["i386", "x86_64"]:
            expect_success("Windows", version, arch, "iso")
    # bad Windows 2000 arch
    expect_fail("Windows", "2000", "x86_64", "iso")
    # bad Windows version
    expect_fail("Windows", "1999", "x86_64", "iso")
    # invalid Windows installtype
    expect_fail("Windows", "2008", "x86_64", "url")

    # OpenSUSE
    for version in ["10.3", "11.0", "11.1", "11.2", "11.3", "11.4", "12.1",
                    "12.2", "12.3"]:
        for arch in ["i386", "x86_64"]:
            expect_success("OpenSUSE", version, arch, "iso")
    # bad OpenSUSE version
    expect_fail("OpenSUSE", "16", "x86_64", "iso")
    # invalid OpenSUSE installtype
    expect_fail("OpenSUSE", "11.4", "x86_64", "url")

    # Ubuntu
    for version in ["5.04", "5.10", "6.06", "6.06.1", "6.06.2", "6.10", "7.04",
                    "7.10", "8.04", "8.04.1", "8.04.2", "8.04.3", "8.04.4",
                    "8.10", "9.04", "9.10", "10.04", "10.04.1", "10.04.2",
                    "10.04.3", "10.10", "11.04", "11.10", "12.04", "12.04.1",
                    "12.04.2", "12.04.3", "12.10", "13.04", "13.10"]:
        for arch in ["i386", "x86_64"]:
            for installtype in ["iso", "url"]:
                expect_success("Ubuntu", version, arch, installtype)
    # bad Ubuntu version
    expect_fail("Ubuntu", "10.9", "i386", "iso")

    # Mandrake
    for version in ["8.2", "9.1", "9.2", "10.0", "10.1"]:
        expect_success("Mandrake", version, "i386", "iso")
    # bad Mandrake version
    expect_fail("Mandrake", "11", "i386", "iso")
    # bad Mandrake arch
    expect_fail("Mandrake", "8.2", "x86_64", "iso")
    # bad Mandrake installtype
    expect_fail("Mandrake", "8.2", "i386", "url")

    # Mandriva
    for version in ["2005", "2006.0", "2007.0", "2008.0"]:
        for arch in ["i386", "x86_64"]:
            expect_success("Mandriva", version, arch, "iso")
    # bad Mandriva version
    expect_fail("Mandriva", "80", "i386", "iso")
    # bad Mandriva installtype
    expect_fail("Mandriva", "2005", "i386", "url")

    # Now run all the tests
    for tst in alltests:
        yield tst.execute()
