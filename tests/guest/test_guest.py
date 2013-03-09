#!/usr/bin/python

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

def default_route():
    route_file = "/proc/net/route"
    d = file(route_file)

    defn = 0
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

tdlxml = """
<template>
  <name>tester</name>
  <os>
    <name>Fedora</name>
    <version>14</version>
    <arch>x86_64</arch>
    <install type='url'>
      <url>http://download.fedoraproject.org/pub/fedora/linux//releases/14/Fedora/x86_64/os/</url>
    </install>
  </os>
</template>
"""

def test_geteltorito_none_src():
    tdl = oz.TDL.TDL(tdlxml)

    config = configparser.SafeConfigParser()
    config.readfp(BytesIO("[libvirt]\nuri=qemu:///session\nbridge_name=%s" % route))

    guest = oz.GuestFactory.guest_factory(tdl, config, None)

    with py.test.raises(oz.OzException.OzException):
        guest._geteltorito(None, None)

def test_geteltorito_none_dst(tmpdir):
    tdl = oz.TDL.TDL(tdlxml)

    config = configparser.SafeConfigParser()
    config.readfp(BytesIO("[libvirt]\nuri=qemu:///session\nbridge_name=%s" % route))

    guest = oz.GuestFactory.guest_factory(tdl, config, None)

    src = os.path.join(str(tmpdir), 'src')
    open(src, 'w').write('src')

    with py.test.raises(oz.OzException.OzException):
        guest._geteltorito(src, None)

def test_geteltorito_short_pvd(tmpdir):
    tdl = oz.TDL.TDL(tdlxml)

    config = configparser.SafeConfigParser()
    config.readfp(BytesIO("[libvirt]\nuri=qemu:///session\nbridge_name=%s" % route))

    guest = oz.GuestFactory.guest_factory(tdl, config, None)

    src = os.path.join(str(tmpdir), 'src')
    open(src, 'w').write('foo')

    dst = os.path.join(str(tmpdir), 'dst')

    with py.test.raises(Exception):
        guest._geteltorito(src, dst)

def test_geteltorito_bogus_pvd_desc(tmpdir):
    tdl = oz.TDL.TDL(tdlxml)

    config = configparser.SafeConfigParser()
    config.readfp(BytesIO("[libvirt]\nuri=qemu:///session\nbridge_name=%s" % route))

    guest = oz.GuestFactory.guest_factory(tdl, config, None)

    src = os.path.join(str(tmpdir), 'src')
    fd = open(src, 'w')
    fd.seek(16*2048)
    fd.write('\0'*128)
    fd.close()

    dst = os.path.join(str(tmpdir), 'dst')

    with py.test.raises(oz.OzException.OzException):
        guest._geteltorito(src, dst)

def test_geteltorito_bogus_pvd_ident(tmpdir):
    tdl = oz.TDL.TDL(tdlxml)

    config = configparser.SafeConfigParser()
    config.readfp(BytesIO("[libvirt]\nuri=qemu:///session\nbridge_name=%s" % route))

    guest = oz.GuestFactory.guest_factory(tdl, config, None)

    src = os.path.join(str(tmpdir), 'src')
    fd = open(src, 'w')
    fd.seek(16*2048)
    fd.write("\x01")
    fd.write('\0'*127)
    fd.close()

    dst = os.path.join(str(tmpdir), 'dst')

    with py.test.raises(oz.OzException.OzException):
        guest._geteltorito(src, dst)

def test_geteltorito_bogus_pvd_unused(tmpdir):
    tdl = oz.TDL.TDL(tdlxml)

    config = configparser.SafeConfigParser()
    config.readfp(BytesIO("[libvirt]\nuri=qemu:///session\nbridge_name=%s" % route))

    guest = oz.GuestFactory.guest_factory(tdl, config, None)

    src = os.path.join(str(tmpdir), 'src')
    fd = open(src, 'w')
    fd.seek(16*2048)
    fd.write("\x01")
    fd.write("CD001")
    fd.write("\0x1")
    fd.write('\0'*127)
    fd.close()

    dst = os.path.join(str(tmpdir), 'dst')

    with py.test.raises(oz.OzException.OzException):
        guest._geteltorito(src, dst)

def test_geteltorito_bogus_pvd_unused2(tmpdir):
    tdl = oz.TDL.TDL(tdlxml)

    config = configparser.SafeConfigParser()
    config.readfp(BytesIO("[libvirt]\nuri=qemu:///session\nbridge_name=%s" % route))

    guest = oz.GuestFactory.guest_factory(tdl, config, None)

    src = os.path.join(str(tmpdir), 'src')
    fd = open(src, 'w')
    fd.seek(16*2048)
    fd.write("\x01")
    fd.write("CD001")
    fd.write("\x01")
    fd.write("\x00")
    fd.write("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
    fd.write("BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB")
    fd.write("\x01")
    fd.write('\0'*127)
    fd.close()

    dst = os.path.join(str(tmpdir), 'dst')

    with py.test.raises(oz.OzException.OzException):
        guest._geteltorito(src, dst)

def test_geteltorito_short_boot_sector(tmpdir):
    tdl = oz.TDL.TDL(tdlxml)

    config = configparser.SafeConfigParser()
    config.readfp(BytesIO("[libvirt]\nuri=qemu:///session\nbridge_name=%s" % route))

    guest = oz.GuestFactory.guest_factory(tdl, config, None)

    src = os.path.join(str(tmpdir), 'src')
    fd = open(src, 'w')
    fd.seek(16*2048)
    fd.write("\x01")
    fd.write("CD001")
    fd.write("\x01")
    fd.write("\x00")
    fd.write("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
    fd.write("BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB")
    fd.write("\x00")
    fd.write('\0'*127)
    fd.close()

    dst = os.path.join(str(tmpdir), 'dst')

    with py.test.raises(Exception):
        guest._geteltorito(src, dst)

def test_geteltorito_bogus_boot_sector(tmpdir):
    tdl = oz.TDL.TDL(tdlxml)

    config = configparser.SafeConfigParser()
    config.readfp(BytesIO("[libvirt]\nuri=qemu:///session\nbridge_name=%s" % route))

    guest = oz.GuestFactory.guest_factory(tdl, config, None)

    src = os.path.join(str(tmpdir), 'src')
    fd = open(src, 'w')
    fd.seek(16*2048)
    fd.write("\x01")
    fd.write("CD001")
    fd.write("\x01")
    fd.write("\x00")
    fd.write("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
    fd.write("BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB")
    fd.write("\x00")
    fd.write('\0'*127)
    fd.seek(17*2048)
    fd.write("\x01")
    fd.write('\0'*75)
    fd.close()

    dst = os.path.join(str(tmpdir), 'dst')

    with py.test.raises(oz.OzException.OzException):
        guest._geteltorito(src, dst)

def test_geteltorito_bogus_boot_isoident(tmpdir):
    tdl = oz.TDL.TDL(tdlxml)

    config = configparser.SafeConfigParser()
    config.readfp(BytesIO("[libvirt]\nuri=qemu:///session\nbridge_name=%s" % route))

    guest = oz.GuestFactory.guest_factory(tdl, config, None)

    src = os.path.join(str(tmpdir), 'src')
    fd = open(src, 'w')
    fd.seek(16*2048)
    fd.write("\x01")
    fd.write("CD001")
    fd.write("\x01")
    fd.write("\x00")
    fd.write("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
    fd.write("BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB")
    fd.write("\x00")
    fd.write('\0'*127)
    fd.seek(17*2048)
    fd.write("\x00")
    fd.write("AAAAA")
    fd.write('\0'*75)
    fd.close()

    dst = os.path.join(str(tmpdir), 'dst')

    with py.test.raises(oz.OzException.OzException):
        guest._geteltorito(src, dst)

def test_geteltorito_bogus_boot_version(tmpdir):
    tdl = oz.TDL.TDL(tdlxml)

    config = configparser.SafeConfigParser()
    config.readfp(BytesIO("[libvirt]\nuri=qemu:///session\nbridge_name=%s" % route))

    guest = oz.GuestFactory.guest_factory(tdl, config, None)

    src = os.path.join(str(tmpdir), 'src')
    fd = open(src, 'w')
    fd.seek(16*2048)
    fd.write("\x01")
    fd.write("CD001")
    fd.write("\x01")
    fd.write("\x00")
    fd.write("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
    fd.write("BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB")
    fd.write("\x00")
    fd.write('\0'*127)
    fd.seek(17*2048)
    fd.write("\x00")
    fd.write("CD001")
    fd.write('\0'*75)
    fd.close()

    dst = os.path.join(str(tmpdir), 'dst')

    with py.test.raises(oz.OzException.OzException):
        guest._geteltorito(src, dst)

def test_geteltorito_bogus_boot_torito(tmpdir):
    tdl = oz.TDL.TDL(tdlxml)

    config = configparser.SafeConfigParser()
    config.readfp(BytesIO("[libvirt]\nuri=qemu:///session\nbridge_name=%s" % route))

    guest = oz.GuestFactory.guest_factory(tdl, config, None)

    src = os.path.join(str(tmpdir), 'src')
    fd = open(src, 'w')
    fd.seek(16*2048)
    fd.write("\x01")
    fd.write("CD001")
    fd.write("\x01")
    fd.write("\x00")
    fd.write("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
    fd.write("BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB")
    fd.write("\x00")
    fd.write('\0'*127)
    fd.seek(17*2048)
    fd.write("\x00")
    fd.write("CD001")
    fd.write("\x01")
    fd.write('\0'*75)
    fd.close()

    dst = os.path.join(str(tmpdir), 'dst')

    with py.test.raises(oz.OzException.OzException):
        guest._geteltorito(src, dst)

def test_geteltorito_bogus_bootp(tmpdir):
    tdl = oz.TDL.TDL(tdlxml)

    config = configparser.SafeConfigParser()
    config.readfp(BytesIO("[libvirt]\nuri=qemu:///session\nbridge_name=%s" % route))

    guest = oz.GuestFactory.guest_factory(tdl, config, None)

    src = os.path.join(str(tmpdir), 'src')
    fd = open(src, 'w')
    fd.seek(16*2048)
    fd.write("\x01")
    fd.write("CD001")
    fd.write("\x01")
    fd.write("\x00")
    fd.write("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
    fd.write("BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB")
    fd.write("\x00")
    fd.write('\0'*127)
    fd.seek(17*2048)
    fd.write("\x00")
    fd.write("CD001")
    fd.write("\x01")
    fd.write("EL TORITO SPECIFICATION")
    fd.write('\0'*41)
    fd.write("\x20\x00\x00\x00")
    fd.close()

    dst = os.path.join(str(tmpdir), 'dst')

    with py.test.raises(Exception):
        guest._geteltorito(src, dst)
