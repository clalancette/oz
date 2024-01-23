#!/usr/bin/python

from __future__ import print_function
import sys
try:
    import configparser
except ImportError:
    import ConfigParser as configparser
try:
    from StringIO import StringIO
except:
    from io import StringIO
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
    import pytest
except ImportError:
    print('Unable to import pytest.  Is pytest installed?')
    sys.exit(1)

def default_route():
    route_file = "/proc/net/route"
    d = open(route_file)

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

def runtest(**kwargs):
    distro = kwargs['distro']
    version = kwargs['version']
    arch = kwargs['arch']
    installtype = kwargs['installtype']
    expect_success = kwargs['expect_success']
    print("Testing %s-%s-%s-%s" % (distro, version, arch, installtype))

    tdlxml = """
<template>
  <name>tester</name>
  <os>
    <name>%s</name>
    <version>%s</version>
    <arch>%s</arch>
    <install type='%s'>
      <%s>file://example.org</%s>
    </install>
    <key>1234</key>
  </os>
</template>
""" % (distro, version, arch, installtype, installtype, installtype)

    success = None
    saved_exc = None
    try:
        tdl = oz.TDL.TDL(tdlxml)

        try:
            config = configparser.SafeConfigParser()
            config.readfp(StringIO("[libvirt]\nuri=qemu:///session\nbridge_name=%s" % route))
        except AttributeError:
            # SafeConfigParser was deprecated in Python 3.2 and
            # readfp was renamed to read_file
            config = configparser.ConfigParser()
            config.read_file(StringIO("[libvirt]\nuri=qemu:///session\nbridge_name=%s" % route))

        if os.getenv('DEBUG') is not None:
            logging.basicConfig(level=logging.DEBUG, format="%(message)s")
        else:
            logging.basicConfig(level=logging.ERROR, format="%(message)s")

            oz.GuestFactory.guest_factory(tdl, config, None)
        if not expect_success:
            assert(False)
    except oz.OzException.OzException as e:
        if expect_success:
            raise

def test_bad_distro():
    runtest(distro='foo', version='1', arch='i386', installtype='url',
            expect_success=False)

def test_bad_installtype():
    runtest(distro='Fedora', version='14', arch='i386', installtype='duh',
            expect_success=False)

def test_bad_arch():
    runtest(distro='Fedora', version='14', arch='ia64', installtype='iso',
            expect_success=False)

def test_fedora_core():
    for version in ["1", "2", "3", "4", "5", "6"]:
        for arch in ["i386", "x86_64"]:
            for installtype in ["url", "iso"]:
                runtest(distro='FedoraCore', version=version, arch=arch,
                        installtype=installtype, expect_success=True)
    runtest(distro='FedoraCore', version='24', arch='x86_64', installtype='iso',
            expect_success=False)
    runtest(distro='FedoraCore', version='6', arch='ia64', installtype='iso',
            expect_success=False)
    runtest(distro='FedoraCore', version='6', arch='x86_64', installtype='foo',
            expect_success=False)

def test_fedora():
    for version in ["7", "8", "9", "10", "11", "12", "13", "14", "15", "16",
                    "17", "18", "19", "20", "21", "22", "23", "24", "25", "26",
                    "27", "28"]:
        for arch in ["i386", "x86_64"]:
            for installtype in ["url", "iso"]:
                runtest(distro='Fedora', version=version, arch=arch,
                        installtype=installtype, expect_success=True)
    runtest(distro='Fedora', version='1', arch='x86_64', installtype='iso',
            expect_success=False)
    runtest(distro='Fedora', version='1', arch='ia64', installtype='iso',
            expect_success=False)
    runtest(distro='Fedora', version='1', arch='x86_64', installtype='foo',
            expect_success=False)

def test_rhl():
    for version in ["7.0", "7.1", "7.2", "7.3", "8", "9"]:
        runtest(distro='RHL', version=version, arch='i386', installtype='url',
                expect_success=True)
    runtest(distro='RHL', version='10', arch='i386', installtype='url',
            expect_success=False)
    runtest(distro='RHL', version='9', arch='x86_64', installtype='url',
            expect_success=False)
    runtest(distro='RHL', version='9', arch='i386', installtype='iso',
            expect_success=False)

def test_rhel21():
    for version in ["GOLD", "U2", "U3", "U4", "U5", "U6"]:
        runtest(distro='RHEL-2.1', version=version, arch='i386',
                installtype='url', expect_success=True)
    runtest(distro='RHEL-2.1', version='U7', arch='i386', installtype='url',
            expect_success=False)
    runtest(distro='RHEL-2.1', version='U6', arch='x86_64', installtype='url',
            expect_success=False)
    runtest(distro='RHEL-2.1', version='U6', arch='i386', installtype='iso',
            expect_success=False)

def test_rhel3():
    for distro in ["RHEL-3", "CentOS-3"]:
        for version in ["GOLD", "U1", "U2", "U3", "U4", "U5", "U6", "U7", "U8",
                        "U9"]:
            for arch in ["i386", "x86_64"]:
                runtest(distro=distro, version=version, arch=arch,
                        installtype='url', expect_success=True)
    runtest(distro='RHEL-3', version='U10', arch='x86_64', installtype='url',
            expect_success=False)
    runtest(distro='RHEL-3', version='U9', arch='ia64', installtype='iso',
            expect_success=False)
    runtest(distro='RHEL-3', version='U9', arch='x86_64', installtype='foo',
            expect_success=False)

def test_rhel4():
    for distro in ["RHEL-4", "CentOS-4", "ScientificLinux-4"]:
        for version in ["GOLD", "U1", "U2", "U3", "U4", "U5", "U6", "U7", "U8",
                        "U9"]:
            for arch in ["i386", "x86_64"]:
                for installtype in ["url", "iso"]:
                    runtest(distro=distro, version=version, arch=arch,
                            installtype=installtype, expect_success=True)
    runtest(distro='RHEL-4', version='U10', arch='x86_64', installtype='url',
            expect_success=False)
    runtest(distro='RHEL-4', version='U9', arch='ia64', installtype='iso',
            expect_success=False)
    runtest(distro='RHEL-4', version='U9', arch='x86_64', installtype='foo',
            expect_success=False)

def test_rhel5():
    for distro in ["RHEL-5", "CentOS-5", "ScientificLinux-5"]:
        for version in ["GOLD", "U1", "U2", "U3", "U4", "U5", "U6", "U7", "U8",
                        "U9", "U10", "U11"]:
            for arch in ["i386", "x86_64"]:
                for installtype in ["url", "iso"]:
                    runtest(distro=distro, version=version, arch=arch,
                            installtype=installtype, expect_success=True)
    runtest(distro='RHEL-5', version='U20', arch='x86_64', installtype='url',
            expect_success=False)
    runtest(distro='RHEL-5', version='U9', arch='ia64', installtype='iso',
            expect_success=False)
    runtest(distro='RHEL-5', version='U9', arch='x86_64', installtype='foo',
            expect_success=False)

def test_rhel6():
    for distro in ["RHEL-6", "CentOS-6", "ScientificLinux-6", "OEL-6"]:
        for version in ["0", "1", "2", "3", "4", "5", "6", "7", "8"]:
            for arch in ["i386", "x86_64"]:
                for installtype in ["url", "iso"]:
                    runtest(distro=distro, version=version, arch=arch,
                            installtype=installtype, expect_success=True)
    runtest(distro='RHEL-6', version='U9', arch='x86_64', installtype='url',
            expect_success=False)
    runtest(distro='RHEL-6', version='8', arch='ia64', installtype='iso',
            expect_success=False)
    runtest(distro='RHEL-6', version='8', arch='x86_64', installtype='foo',
            expect_success=False)

def test_rhel7():
    for distro in ["RHEL-7", "CentOS-7"]:
        for version in ["0", "1", "2"]:
            for arch in ["i386", "x86_64"]:
                for installtype in ["url", "iso"]:
                    runtest(distro=distro, version=version, arch=arch,
                            installtype=installtype, expect_success=True)
    runtest(distro='RHEL-7', version='U9', arch='x86_64', installtype='url',
            expect_success=False)
    runtest(distro='RHEL-7', version='2', arch='ia64', installtype='iso',
            expect_success=False)
    runtest(distro='RHEL-7', version='2', arch='x86_64', installtype='foo',
            expect_success=False)

def test_debian():
    for version in ["5", "6", "7", "8", "9"]:
        for arch in ["i386", "x86_64"]:
            runtest(distro='Debian', version=version, arch=arch,
                    installtype='iso', expect_success=True)
    runtest(distro='Debian', version='U9', arch='x86_64', installtype='url',
            expect_success=False)
    runtest(distro='Debian', version='9', arch='ia64', installtype='iso',
            expect_success=False)
    runtest(distro='Debian', version='9', arch='x86_64', installtype='foo',
            expect_success=False)

def test_windows():
    runtest(distro='Windows', version='2000', arch='i386', installtype='iso',
            expect_success=True)
    for version in ["XP", "2003", "2008", "7", "8", "2012", "8.1", "2016", "10"]:
        for arch in ["i386", "x86_64"]:
            runtest(distro='Windows', version=version, arch=arch, installtype='iso',
                    expect_success=True)
    runtest(distro='Windows', version='U9', arch='x86_64', installtype='iso',
            expect_success=False)
    runtest(distro='Windows', version='2012', arch='ia64', installtype='iso',
            expect_success=False)
    runtest(distro='Windows', version='2012', arch='x86_64', installtype='foo',
            expect_success=False)
    runtest(distro='Windows', version='2000', arch='x86_64', installtype='iso',
            expect_success=False)

def test_opensuse():
    for version in ["10.3", "11.0", "11.1", "11.2", "11.3", "11.4", "12.1",
                    "12.2", "12.3", "13.1", "13.2"]:
        for arch in ["i386", "x86_64"]:
            runtest(distro='OpenSUSE', version=version, arch=arch, installtype='iso',
                    expect_success=True)
    runtest(distro='OpenSUSE', version='U9', arch='x86_64', installtype='iso',
            expect_success=False)
    runtest(distro='OpenSUSE', version='13.2', arch='ia64', installtype='iso',
            expect_success=False)
    runtest(distro='OpenSUSE', version='13.2', arch='x86_64', installtype='foo',
            expect_success=False)

def test_ubuntu():
    for version in ["5.04", "5.10", "6.06", "6.06.1", "6.06.2", "6.10", "7.04",
                    "7.10", "8.04", "8.04.1", "8.04.2", "8.04.3", "8.04.4",
                    "8.10", "9.04", "9.10", "10.04", "10.04.1", "10.04.2",
                    "10.04.3", "10.10", "11.04", "11.10", "12.04", "12.04.1",
                    "12.04.2", "12.04.3", "12.10", "13.04", "13.10", "14.04",
                    "14.10", "15.04", "15.10", "16.04", "16.10", "17.04",
                    "17.10", "18.04"]:
        for arch in ["i386", "x86_64"]:
            for installtype in ["iso", "url"]:
                runtest(distro='Ubuntu', version=version, arch=arch,
                        installtype=installtype, expect_success=True)
    runtest(distro='Ubuntu', version='U9', arch='x86_64', installtype='iso',
            expect_success=False)
    runtest(distro='Ubuntu', version='16.04', arch='ia64', installtype='iso',
            expect_success=False)
    runtest(distro='Ubuntu', version='16.04', arch='x86_64', installtype='foo',
            expect_success=False)

def test_mandrake():
    for version in ["8.2", "9.1", "9.2", "10.0", "10.1"]:
        runtest(distro='Mandrake', version=version, arch='i386',
                installtype='iso', expect_success=True)
    runtest(distro='Mandrake', version='U9', arch='x86_64', installtype='iso',
            expect_success=False)
    runtest(distro='Mandrake', version='10.1', arch='ia64', installtype='iso',
            expect_success=False)
    runtest(distro='Mandrake', version='10.1', arch='x86_64', installtype='foo',
            expect_success=False)
    runtest(distro='Mandrake', version='10.1', arch='x86_64', installtype='url',
            expect_success=False)

def test_mandriva():
    for version in ["2005", "2006.0", "2007.0", "2008.0"]:
        for arch in ["i386", "x86_64"]:
            runtest(distro='Mandriva', version=version, arch=arch,
                    installtype='iso', expect_success=True)
    runtest(distro='Mandriva', version='U9', arch='x86_64', installtype='iso',
            expect_success=False)
    runtest(distro='Mandriva', version='2008.0', arch='ia64', installtype='iso',
            expect_success=False)
    runtest(distro='Mandriva', version='2008.0', arch='x86_64', installtype='foo',
            expect_success=False)
    runtest(distro='Mandriva', version='2008.0', arch='x86_64', installtype='url',
            expect_success=False)

def test_mageia():
    for version in ["2", "3", "4", "4.1", "5"]:
        for arch in ["i386", "x86_64"]:
            runtest(distro='Mageia', version=version, arch=arch,
                    installtype='iso', expect_success=True)
    runtest(distro='Mageia', version='U9', arch='x86_64', installtype='iso',
            expect_success=False)
    runtest(distro='Mageia', version='5', arch='ia64', installtype='iso',
            expect_success=False)
    runtest(distro='Mageia', version='5', arch='x86_64', installtype='foo',
            expect_success=False)
