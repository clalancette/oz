#!/usr/bin/python

import sys
import getpass
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

def setup_guest(xml, macaddress=None):
    tdl = oz.TDL.TDL(xml)

    try:
        config = configparser.SafeConfigParser()
        config.readfp(StringIO("[libvirt]\nuri=qemu:///session\nbridge_name=%s" % route))
    except AttributeError:
        # SafeConfigParser was deprecated in Python 3.2 and readfp
        # was renamed to read_file
        config = configparser.ConfigParser()
        config.read_file(StringIO("[libvirt]\nuri=qemu:///session\nbridge_name=%s" % route))

    guest = oz.GuestFactory.guest_factory(tdl, config, None, macaddress=macaddress)
    return guest

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

tdlxml2 = """
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
  <disk>
    <size>20</size>
  </disk>
</template>
"""


def test_geteltorito_none_src():
    guest = setup_guest(tdlxml)

    with pytest.raises(oz.OzException.OzException):
        guest._geteltorito(None, None)

def test_geteltorito_none_dst(tmpdir):
    guest = setup_guest(tdlxml)

    src = os.path.join(str(tmpdir), 'src')
    open(src, 'w').write('src')

    with pytest.raises(oz.OzException.OzException):
        guest._geteltorito(src, None)

def test_geteltorito_short_pvd(tmpdir):
    guest = setup_guest(tdlxml)

    src = os.path.join(str(tmpdir), 'src')
    open(src, 'w').write('foo')

    dst = os.path.join(str(tmpdir), 'dst')

    with pytest.raises(Exception):
        guest._geteltorito(src, dst)

def test_geteltorito_bogus_pvd_desc(tmpdir):
    guest = setup_guest(tdlxml)

    src = os.path.join(str(tmpdir), 'src')
    fd = open(src, 'w')
    fd.seek(16*2048)
    fd.write('\0'*128)
    fd.close()

    dst = os.path.join(str(tmpdir), 'dst')

    with pytest.raises(oz.OzException.OzException):
        guest._geteltorito(src, dst)

def test_geteltorito_bogus_pvd_ident(tmpdir):
    guest = setup_guest(tdlxml)

    src = os.path.join(str(tmpdir), 'src')
    fd = open(src, 'w')
    fd.seek(16*2048)
    fd.write("\x01")
    fd.write('\0'*127)
    fd.close()

    dst = os.path.join(str(tmpdir), 'dst')

    with pytest.raises(oz.OzException.OzException):
        guest._geteltorito(src, dst)

def test_geteltorito_bogus_pvd_unused(tmpdir):
    guest = setup_guest(tdlxml)

    src = os.path.join(str(tmpdir), 'src')
    fd = open(src, 'w')
    fd.seek(16*2048)
    fd.write("\x01")
    fd.write("CD001")
    fd.write("\0x1")
    fd.write('\0'*127)
    fd.close()

    dst = os.path.join(str(tmpdir), 'dst')

    with pytest.raises(oz.OzException.OzException):
        guest._geteltorito(src, dst)

def test_geteltorito_bogus_pvd_unused2(tmpdir):
    guest = setup_guest(tdlxml)

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

    with pytest.raises(oz.OzException.OzException):
        guest._geteltorito(src, dst)

def test_geteltorito_short_boot_sector(tmpdir):
    guest = setup_guest(tdlxml)

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

    with pytest.raises(Exception):
        guest._geteltorito(src, dst)

def test_geteltorito_bogus_boot_sector(tmpdir):
    guest = setup_guest(tdlxml)

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

    with pytest.raises(oz.OzException.OzException):
        guest._geteltorito(src, dst)

def test_geteltorito_bogus_boot_isoident(tmpdir):
    guest = setup_guest(tdlxml)

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

    with pytest.raises(oz.OzException.OzException):
        guest._geteltorito(src, dst)

def test_geteltorito_bogus_boot_version(tmpdir):
    guest = setup_guest(tdlxml)

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

    with pytest.raises(oz.OzException.OzException):
        guest._geteltorito(src, dst)

def test_geteltorito_bogus_boot_torito(tmpdir):
    guest = setup_guest(tdlxml)

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

    with pytest.raises(oz.OzException.OzException):
        guest._geteltorito(src, dst)

def test_geteltorito_bogus_bootp(tmpdir):
    guest = setup_guest(tdlxml)

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

    with pytest.raises(Exception):
        guest._geteltorito(src, dst)

def test_init_guest():
    guest = setup_guest(tdlxml2)

    # size without units is taken to be GiB
    assert guest.disksize == 20*(2**30)
    assert guest.image_name() == 'tester'
    assert guest.output_image_path() in (
        # user's image storage
        '%s/.oz/images/tester.dsk' % os.getenv('HOME'),
        # system image storage (when testing as root, I think)
        '/var/lib/libvirt/images/tester.dsk'
    )
    assert guest.default_auto_file() == True

def test_init_guest_bad_arch():
    tdl = oz.TDL.TDL(tdlxml)
    tdl.arch = 'armhf'  # Done here to make sure the TDL class doesn't error
    try:
        config = configparser.SafeConfigParser()
        config.readfp(StringIO("[libvirt]\nuri=qemu:///session\nbridge_name=%s" % route))
    except AttributeError:
        # SafeConfigParser was deprecated in Python 3.2 and readfp
        # was renamed to read_file
        config = configparser.ConfigParser()
        config.read_file(StringIO("[libvirt]\nuri=qemu:///session\nbridge_name=%s" % route))

    with pytest.raises(Exception):
        oz.GuestFactory.guest_factory(tdl, config, None)

def test_icicle_generation():
    guest = setup_guest(tdlxml)
    with open(os.path.dirname(__file__) + '/test.icicle', 'r') as handle:
        test_icicle = handle.read()

    packages = [
        "accountsservice",
        "adduser",
        "apparmor",
        "apt",
        "apt-transport-https",
        "apt-utils",
        "apt-xapian-index",
        "aptitude",
        "at",
        "base-files",
        "base-passwd",
        "bash",
        "bash-completion",
        "bind9-host",
        "binutils",
        "bsdmainutils",
        "bsdutils",
        "build-essential",
        "busybox-initramfs",
        "busybox-static",
        "bzip2",
        "ca-certificates",
        "chef",
        "cloud-init",
        "cloud-initramfs-growroot",
        "cloud-initramfs-rescuevol",
        "cloud-utils",
        "comerr-dev",
        "console-setup",
        "coreutils",
        "cpio",
        "cpp",
        "cpp-4.6",
        "crda",
        "cron",
        "curl",
        "dash",
        "dbus",
        "debconf",
        "debconf-i18n",
        "debianutils",
        "denyhosts",
        "diffutils",
        "discover",
        "discover-data",
        "dkms",
        "dmidecode",
        "dmsetup",
        "dnsutils",
        "dosfstools",
        "dpkg",
        "dpkg-dev",
        "e2fslibs",
        "e2fsprogs",
        "ed",
        "eject",
        "euca2ools",
        "fakeroot",
        "file",
        "findutils",
        "friendly-recovery",
        "ftp",
        "fuse",
        "g++",
        "g++-4.6"
    ]

    icicle = guest._output_icicle_xml(packages, 'Icicle Description')
    assert test_icicle == icicle

def test_xml_generation_1():
    # Provide a macaddress so testing is easier
    guest = setup_guest(tdlxml, macaddress='52:54:00:04:cc:a6')

    with open(os.path.dirname(__file__) + '/libvirt/test_xml_generation_1.xml', 'r') as handle:
        test_xml = handle.read()

    # Replace various smaller items as they are auto generated
    test_xml = test_xml % (guest.libvirt_type, guest.uuid, route, guest.listen_port, guest.diskimage)
    # drop host-passthrough line if libvirt_type is not kvm
    if guest.libvirt_type != "kvm":
        test_xml = "\n".join((line for line in test_xml.splitlines() if "host-passthrough" not in line)) + "\n"

    bootdev = 'hd'
    installdev = None
    libvirt = guest._generate_xml(bootdev, installdev)

    assert test_xml == libvirt

def test_xml_generation_2():
    # Provide a macaddress so testing is easier
    guest = setup_guest(tdlxml, macaddress='52:54:00:04:cc:a6')

    with open(os.path.dirname(__file__) + '/libvirt/test_xml_generation_2.xml', 'r') as handle:
        test_xml = handle.read()

    # Replace various smaller items as they are auto generated
    test_xml = test_xml % (guest.libvirt_type, guest.uuid, route, guest.listen_port, guest.diskimage)
    # drop host-passthrough line if libvirt_type is not kvm
    if guest.libvirt_type != "kvm":
        test_xml = "\n".join((line for line in test_xml.splitlines() if "host-passthrough" not in line)) + "\n"

    bootdev = 'hd'
    installdev = guest._InstallDev('blue', '/var/bin/foo', 'muni')
    libvirt = guest._generate_xml(bootdev, installdev, kernel='kernel option', initrd='initrd option', cmdline='command line')

    assert test_xml == libvirt

def test_get_disks_and_interfaces():
    # Provide a macaddress so testing is easier
    guest = setup_guest(tdlxml, macaddress='52:54:00:04:cc:a6')

    path = os.path.dirname(__file__) + '/libvirt/test_get_disks_and_interfaces.xml'

    # Get the comparision xml
    with open(path, 'r') as handle:
        # Replace various smaller items as they are auto generated
        test_xml = handle.read() % (guest.uuid, route, guest.listen_port, guest.diskimage)
        disks, interfaces = guest._get_disks_and_interfaces(test_xml)

    assert disks == ['vda']
    assert interfaces == ['vnet7']

def test_get_disks_and_interfaces_missing_interface_target():
    # Provide a macaddress so testing is easier
    guest = setup_guest(tdlxml, macaddress='52:54:00:04:cc:a6')

    path = os.path.dirname(__file__) + '/libvirt/test_get_disks_and_interfaces_missing_interface_target.xml'

    # Get the comparision xml
    with open(path, 'r') as handle:
        with pytest.raises(Exception):
            # Replace various smaller items as they are auto generated
            test_xml = handle.read() % (guest.uuid, route, guest.listen_port, guest.diskimage)
            guest._get_disks_and_interfaces(test_xml)

def test_get_disks_and_interfaces_missing_interface_target_device():
    # Provide a macaddress so testing is easier
    guest = setup_guest(tdlxml, macaddress='52:54:00:04:cc:a6')

    path = os.path.dirname(__file__) + '/libvirt/test_get_disks_and_interfaces_missing_interface_target_device.xml'

    # Get the comparision xml
    with open(path, 'r') as handle:
        with pytest.raises(Exception):
            # Replace various smaller items as they are auto generated
            test_xml = handle.read() % (guest.uuid, route, guest.listen_port, guest.diskimage)
            guest._get_disks_and_interfaces(test_xml)

def test_get_disks_and_interfaces_missing_disk_target():
    # Provide a macaddress so testing is easier
    guest = setup_guest(tdlxml, macaddress='52:54:00:04:cc:a6')

    path = os.path.dirname(__file__) + '/libvirt/test_get_disks_and_interfaces_missing_disk_target.xml'

    # Get the comparision xml
    with open(path, 'r') as handle:
        with pytest.raises(Exception):
            # Replace various smaller items as they are auto generated
            test_xml = handle.read() % (guest.uuid, route, guest.listen_port, guest.diskimage)
            guest._get_disks_and_interfaces(test_xml)

def test_get_disks_and_interfaces_missing_disk_target_device():
    # Provide a macaddress so testing is easier
    guest = setup_guest(tdlxml, macaddress='52:54:00:04:cc:a6')

    # Get the comparision xml
    path = os.path.dirname(__file__) + '/libvirt/test_get_disks_and_interfaces_missing_disk_target_device.xml'
    with open(path, 'r') as handle:
        with pytest.raises(Exception):
            # Replace various smaller items as they are auto generated
            test_xml = handle.read() % (guest.uuid, route, guest.listen_port, guest.diskimage)
            guest._get_disks_and_interfaces(test_xml)

def test_modify_libvirt_xml_for_serial():
    # Provide a macaddress so testing is easier
    guest = setup_guest(tdlxml, macaddress='52:54:00:04:cc:a6')

    # Get the comparision xml
    path = os.path.dirname(__file__) + '/libvirt/test_modify_libvirt_xml_for_serial.xml'
    with open(path, 'r') as handle:
        # Replace various smaller items as they are auto generated
        test_xml = handle.read() % (guest.uuid, route, guest.listen_port, guest.diskimage)
        final = guest._modify_libvirt_xml_for_serial(test_xml)

    path = os.path.dirname(__file__) + '/libvirt/test_modify_libvirt_xml_for_serial_final.xml'
    with open(path, 'r') as handle:
        # Replace various smaller items as they are auto generated
        final_xml = handle.read() % (guest.uuid, route, guest.diskimage, guest.listen_port)
        assert final_xml == final

def test_modify_libvirt_xml_for_serial_too_many_targets():
    # Provide a macaddress so testing is easier
    guest = setup_guest(tdlxml, macaddress='52:54:00:04:cc:a6')

    # Get the comparision xml
    path = os.path.dirname(__file__) + '/libvirt/test_modify_libvirt_xml_for_serial_too_many_targets.xml'
    with open(path, 'r') as handle:
        with pytest.raises(Exception):
            # Replace various smaller items as they are auto generated
            test_xml = handle.read() % (guest.uuid, route, guest.listen_port, guest.diskimage)
            guest._modify_libvirt_xml_for_serial(test_xml)

def test_modify_libvirt_xml_for_serial_missing_devices():
    # Provide a macaddress so testing is easier
    guest = setup_guest(tdlxml, macaddress='52:54:00:04:cc:a6')

    # Get the comparision xml
    path = os.path.dirname(__file__) + '/libvirt/test_modify_libvirt_xml_for_serial_missing_devices.xml'
    with open(path, 'r') as handle:
        with pytest.raises(Exception):
            # Replace various smaller items as they are auto generated
            test_xml = handle.read() % (guest.uuid, route, guest.listen_port, guest.diskimage)
            guest._modify_libvirt_xml_for_serial(test_xml)

def test_modify_libvirt_xml_for_serial_too_many_devices():
    # Provide a macaddress so testing is easier
    guest = setup_guest(tdlxml, macaddress='52:54:00:04:cc:a6')

    # Get the comparision xml
    path = os.path.dirname(__file__) + '/libvirt/test_modify_libvirt_xml_for_serial_too_many_devices.xml'
    with open(path, 'r') as handle:
        with pytest.raises(Exception):
            # Replace various smaller items as they are auto generated
            test_xml = handle.read() % (guest.uuid, route, guest.listen_port, guest.diskimage)
            guest._modify_libvirt_xml_for_serial(test_xml)


def test_modify_libvirt_xml_diskimage():
    # Provide a macaddress so testing is easier
    guest = setup_guest(tdlxml, macaddress='52:54:00:04:cc:a6')

    # Get the comparision xml
    path = os.path.dirname(__file__) + '/libvirt/test_modify_libvirt_xml_diskimage.xml'
    with open(path, 'r') as handle:
        # Replace various smaller items as they are auto generated
        test_xml = handle.read() % (guest.uuid, route, guest.listen_port, guest.diskimage)

        name, ext = os.path.splitext(guest.diskimage)
        image = name + '.qcow2'
        final = guest._modify_libvirt_xml_diskimage(test_xml, image, 'qcow2')

    path = os.path.dirname(__file__) + '/libvirt/test_modify_libvirt_xml_diskimage_final.xml'
    with open(path, 'r') as handle:
        # Replace various smaller items as they are auto generated
        final_xml = handle.read() % (guest.uuid, route, guest.listen_port, image)
        assert final_xml == final

def test_modify_libvirt_xml_diskimage_missing_disk_source():
    # Provide a macaddress so testing is easier
    guest = setup_guest(tdlxml, macaddress='52:54:00:04:cc:a6')

    # Get the comparision xml
    path = os.path.dirname(__file__) + '/libvirt/test_modify_libvirt_xml_diskimage_missing_disk_source.xml'
    with open(path, 'r') as handle:
        with pytest.raises(Exception):
            # Replace various smaller items as they are auto generated
            test_xml = handle.read() % (guest.uuid, route, guest.listen_port, guest.diskimage)
            guest._modify_libvirt_xml_diskimage(test_xml, guest.diskimage, 'qcow2')

def test_modify_libvirt_xml_diskimage_too_many_drivers():
    # Provide a macaddress so testing is easier
    guest = setup_guest(tdlxml, macaddress='52:54:00:04:cc:a6')

    # Get the comparision xml
    path = os.path.dirname(__file__) + '/libvirt/test_modify_libvirt_xml_diskimage_too_many_drivers.xml'
    with open(path, 'r') as handle:
        with pytest.raises(Exception):
            # Replace various smaller items as they are auto generated
            test_xml = handle.read() % (guest.uuid, route, guest.listen_port, guest.diskimage)
            guest._modify_libvirt_xml_diskimage(test_xml, guest.diskimage, 'qcow2')
