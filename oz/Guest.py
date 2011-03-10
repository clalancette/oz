# Copyright (C) 2010,2011  Chris Lalancette <clalance@redhat.com>

# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.

# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.

# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA

import uuid
import libvirt
import os
import subprocess
import shutil
import time
import pycurl
import urllib2
import stat
import libxml2
import logging
import random
import guestfs
import socket
import select
import struct
import numpy
import tempfile

import ozutil
import OzException

def libvirt_error_handler(ctxt, err):
    pass

# NOTE: python 2.7 already defines subprocess.capture_output, but I can't
# depend on that yet.  So write my own
def subprocess_check_output(*popenargs, **kwargs):
    if 'stdout' in kwargs:
        raise ValueError('stdout argument not allowed, it will be overridden.')
    if 'stderr' in kwargs:
        raise ValueError('stderr argument not allowed, it will be overridden.')

    ozutil.executable_exists(popenargs[0][0])

    # NOTE: it is very, very important that we use temporary files for
    # collecting stdout and stderr here.  There is a nasty bug in python
    # subprocess; if your process produces more than 64k of data on an fd that
    # is using subprocess.PIPE, the whole thing will hang. To avoid this, we
    # use temporary fds to capture the data
    stdouttmp = tempfile.TemporaryFile()
    stderrtmp = tempfile.TemporaryFile()

    process = subprocess.Popen(stdout=stdouttmp, stderr=stderrtmp, *popenargs,
                               **kwargs)
    process.communicate()
    retcode = process.poll()

    stdouttmp.seek(0, 0)
    stdout = stdouttmp.read()
    stdouttmp.close()

    stderrtmp.seek(0, 0)
    stderr = stderrtmp.read()
    stderrtmp.close()

    if retcode:
        cmd = ' '.join(*popenargs)
        raise OzException.OzException("'%s' failed(%d): %s" % (cmd, retcode, stderr))
    return (stdout, stderr, retcode)

class Guest(object):
    def get_conf(self, config, section, key, default):
        if config is not None and config.has_section(section) \
                and config.has_option(section, key):
            return config.get(section, key)
        else:
            return default

    def get_boolean_conf(self, config, section, key, default):
        value = self.get_conf(config, section, key, None)
        if value is None:
            value = default
        elif value.lower() == 'true' or value.lower() == 'yes':
            value = True
        elif value.lower() == 'false' or value.lower() == 'no':
            value = False
        else:
            raise OzException.OzException("Configuration parameter '%s' must be True, Yes, False, or No" % (key))

        return value

    def __init__(self, name, distro, update, arch, nicmodel, clockoffset,
                 mousetype, diskbus, config):
        if arch != "i386" and arch != "x86_64":
            raise OzException.OzException("Unsupported guest arch " + arch)
        self.log = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))
        self.uuid = uuid.uuid4()
        mac = [0x52, 0x54, 0x00, random.randint(0x00, 0xff),
               random.randint(0x00, 0xff), random.randint(0x00, 0xff)]
        self.macaddr = ':'.join(map(lambda x:"%02x" % x, mac))
        self.distro = distro
        self.update = update
        self.arch = arch
        self.name = name

        self.output_dir = self.get_conf(config, 'paths', 'output_dir',
                                        '/var/lib/libvirt/images')

        self.data_dir = self.get_conf(config, 'paths', 'data_dir',
                                      '/var/lib/oz')

        self.libvirt_uri = self.get_conf(config, 'libvirt', 'uri',
                                         'qemu:///system')

        self.libvirt_type = self.get_conf(config, 'libvirt', 'type', 'kvm')

        self.cache_original_media = self.get_boolean_conf(config, 'cache',
                                                          'original_media',
                                                          True)
        self.cache_modified_media = self.get_boolean_conf(config, 'cache',
                                                          'modified_media',
                                                          False)

        self.cache_jeos = self.get_boolean_conf(config, 'cache', 'jeos', False)
        self.jeos_cache_dir = os.path.join(self.data_dir, "jeos")
        self.jeos_filename = os.path.join(self.jeos_cache_dir,
                                          self.distro + self.update + self.arch + ".dsk")

        self.diskimage = os.path.join(self.output_dir, self.name + ".dsk")
        self.icicle_tmp = os.path.join(self.data_dir, "icicletmp", self.name)
        self.listen_port = random.randrange(1024, 65535)
        libvirt.registerErrorHandler(libvirt_error_handler, 'context')
        self.libvirt_conn = libvirt.open(self.libvirt_uri)

        # we have to make sure that the private libvirt bridge is available
        self.host_bridge_ip = None
        self.bridge_name = None
        for netname in self.libvirt_conn.listNetworks():
            network = self.libvirt_conn.networkLookupByName(netname)

            xml = network.XMLDesc(0)
            doc = libxml2.parseMemory(xml, len(xml))

            forward = doc.xpathEval('/network/forward')
            if len(forward) != 1:
                self.log.warn("Libvirt network without a forward element, skipping")
                continue

            if forward[0].prop('mode') == 'nat':
                ip = doc.xpathEval('/network/ip')
                if len(ip) != 1:
                    self.log.warn("Libvirt network without an IP, skipping")
                    continue
                self.host_bridge_ip = ip[0].prop('address')
                self.bridge_name = network.bridgeName()
                break

        if self.bridge_name is None or self.host_bridge_ip is None:
            raise OzException.OzException("Could not find a viable libvirt NAT bridge, install cannot continue")

        self.nicmodel = nicmodel
        if self.nicmodel is None:
            self.nicmodel = "rtl8139"
        self.clockoffset = clockoffset
        if self.clockoffset is None:
            self.clockoffset = "utc"
        self.mousetype = mousetype
        if self.mousetype is None:
            self.mousetype = "ps2"
        if diskbus is None or diskbus == "ide":
            self.disk_bus = "ide"
            self.disk_dev = "hda"
        elif diskbus == "virtio":
            self.disk_bus = "virtio"
            self.disk_dev = "vda"
        else:
            raise OzException.OzException("Unknown diskbus type " + diskbus)

        self.log.debug("Name: %s, UUID: %s" % (self.name, self.uuid))
        self.log.debug("MAC: %s, distro: %s" % (self.macaddr, self.distro))
        self.log.debug("update: %s, arch: %s, diskimage: %s" % (self.update, self.arch, self.diskimage))
        self.log.debug("host IP: %s, nicmodel: %s, clockoffset: %s" % (self.host_bridge_ip, self.nicmodel, self.clockoffset))
        self.log.debug("mousetype: %s, disk_bus: %s, disk_dev: %s" % (self.mousetype, self.disk_bus, self.disk_dev))
        self.log.debug("icicletmp: %s, listen_port: %d" % (self.icicle_tmp, self.listen_port))
        self.log.debug("Cache original media?: %s" % (self.cache_original_media))

    def cleanup_old_guest(self):
        self.log.info("Cleaning up guest named %s" % (self.name))
        try:
            dom = self.libvirt_conn.lookupByName(self.name)
            try:
                dom.destroy()
            except:
                pass
            dom.undefine()
        except:
            pass

        if os.access(self.diskimage, os.F_OK):
            os.unlink(self.diskimage)

    def check_for_guest_conflict(self):
        # this method checks if anything we are going to do will conflict
        # with what already exists.  In particular, if a guest with the same
        # name, UUID, or diskimage already exists, we'll raise an exception
        self.log.info("Checking for guest conflicts with %s" % (self.name))

        try:
            dom = self.libvirt_conn.lookupByName(self.name)
            raise OzException.OzException("Domain with name %s already exists" % (self.name))
        except:
           pass

        try:
            dom = self.libvirt_conn.lookupByUUID(self.uuid)
            raise OzException.OzException("Domain with UUID %s already exists" % (self.uuid))
        except:
            pass

        if os.access(self.diskimage, os.F_OK):
            raise OzException.OzException("Diskimage %s already exists" % (self.diskimage))

    # the next 4 methods are intended to be overridden by the individual
    # OS backends; raise an error if they are called but not implemented
    def generate_install_media(self, force_download=False):
        raise OzException.OzException("Install media for %s%s is not implemented, install cannot continue" % (self.distro, self.update))

    def customize(self, libvirt_xml):
        raise OzException.OzException("Customization for %s%s is not implemented" % (self.distro, self.update))

    def generate_icicle(self, libvirt_xml):
        raise OzException.OzException("ICICLE generation for %s%s is not implemented" % (self.distro, self.update))

    # this method is intended to be an optimization if the user wants to do
    # both customize and generate_icicle
    def customize_and_generate_icicle(self, libvirt_xml):
        raise OzException.OzException("Customization and ICICLE generate for %s%s is not implemented" % (self.distro, self.update))

    def jeos(self, skip_jeos=True):
        if not skip_jeos and os.access(self.jeos_cache_dir, os.F_OK) and os.access(self.jeos_filename, os.F_OK):
            self.log.info("Found cached JEOS, using it")
            ozutil.copyfile_sparse(self.jeos_filename, self.diskimage)
            return self.generate_xml("hd", want_install_disk=False)
        return None

    def targetDev(self, doc, devicetype, path, bus):
        install = doc.newChild(None, "disk", None)
        install.setProp("type", "file")
        install.setProp("device", devicetype)
        source = install.newChild(None, "source", None)
        source.setProp("file", path)
        target = install.newChild(None, "target", None)
        target.setProp("dev", bus)

    def generate_xml(self, bootdev, want_install_disk=True):
        self.log.info("Generate XML for guest %s with bootdev %s" % (self.name, bootdev))

        # create XML document
        doc = libxml2.newDoc("1.0")

        # create top-level domain element
        domain = doc.newChild(None, "domain", None)
        domain.setProp("type", self.libvirt_type)

        # create name element
        name = domain.newChild(None, "name", self.name)

        # create memory elements
        memory = domain.newChild(None, "memory", "1048576")
        currentMemory = domain.newChild(None, "currentMemory", "1048576")

        # create uuid
        uuid = domain.newChild(None, "uuid", str(self.uuid))

        # create clock offset
        clock = domain.newChild(None, "clock", None)
        clock.setProp("offset", self.clockoffset)

        # create vcpu
        vcpu = domain.newChild(None, "vcpu", "1")

        # create features
        features = domain.newChild(None, "features", None)
        acpi = features.newChild(None, "acpi", None)
        apic = features.newChild(None, "apic", None)
        pae = features.newChild(None, "pae", None)

        # create os
        osNode = domain.newChild(None, "os", None)
        ostype = osNode.newChild(None, "type", "hvm")
        boot = osNode.newChild(None, "boot", None)
        boot.setProp("dev", bootdev)

        # create poweroff, reboot, crash
        poweroff = domain.newChild(None, "on_poweroff", "destroy")
        reboot = domain.newChild(None, "on_reboot", "destroy")
        crash = domain.newChild(None, "on_crash", "destroy")

        # create devices
        devices = domain.newChild(None, "devices", None)
        # console
        console = devices.newChild(None, "console", None)
        console.setProp("device", "pty")
        # graphics
        graphics = devices.newChild(None, "graphics", None)
        graphics.setProp("port", "-1")
        graphics.setProp("type", "vnc")
        # network
        interface = devices.newChild(None, "interface", None)
        interface.setProp("type", "bridge")
        interfaceSource = interface.newChild(None, "source", None)
        interfaceSource.setProp("bridge", self.bridge_name)
        interfaceMac = interface.newChild(None, "mac", None)
        interfaceMac.setProp("address", self.macaddr)
        interfaceModel = interface.newChild(None, "model", None)
        interfaceModel.setProp("type", self.nicmodel)
        # input
        inputdev = devices.newChild(None, "input", None)
        if self.mousetype == "ps2":
            inputdev.setProp("bus", "ps2")
            inputdev.setProp("type", "mouse")
        elif self.mousetype == "usb":
            inputdev.setProp("type", "tablet")
            inputdev.setProp("bus", "usb")
        # console
        console = devices.newChild(None, "console", None)
        console.setProp("type", "pty")
        consoleTarget = console.newChild(None, "target", None)
        consoleTarget.setProp("port", "0")
        # boot disk
        bootDisk = devices.newChild(None, "disk", None)
        bootDisk.setProp("device", "disk")
        bootDisk.setProp("type", "file")
        bootTarget = bootDisk.newChild(None, "target", None)
        bootTarget.setProp("dev", self.disk_dev)
        bootTarget.setProp("bus", self.disk_bus)
        bootSource = bootDisk.newChild(None, "source", None)
        bootSource.setProp("file", self.diskimage)
        # install disk (cdrom or floppy)
        if want_install_disk:
            if hasattr(self, "output_iso"):
                self.targetDev(devices, "cdrom", self.output_iso, "hdc")
            if hasattr(self, "output_floppy"):
                self.targetDev(devices, "floppy", self.output_floppy, "fda")

        self.log.debug("Generated XML:\n%s" % (doc.serialize(None, 1)))

        return doc.serialize(None, 1)

    def generate_blank_diskimage(self, size=10):
        self.log.info("Generating %dGB blank diskimage for %s" % (size, self.name))
        f = open(self.diskimage, "w")
        # 10 GB disk image by default
        f.truncate(size * 1024 * 1024 * 1024)
        f.close()

    def generate_diskimage(self, size=10):
        self.log.info("Generating %dGB diskimage with fake partition for %s" % (size, self.name))
        # FIXME: I think that this partition table will only work with the 10GB
        # image.  We'll need to do something more sophisticated when we handle
        # variable sized disks
        f = open(self.diskimage, "w")
        f.seek(0x1bf)
        f.write("\x01\x01\x00\x82\xfe\x3f\x7c\x3f\x00\x00\x00\xfe\xa3\x1e")
        f.seek(0x1fe)
        f.write("\x55\xaa")
        f.seek(size * 1024 * 1024 * 1024)
        f.write("\x00")
        f.close()

    def wait_for_install_finish(self, libvirt_dom, count):
        origcount = count
        while count > 0:
            if count % 10 == 0:
                self.log.debug("Waiting for %s to finish installing, %d/%d" % (self.name, count, origcount))
            try:
                info = libvirt_dom.info()
            except libvirt.libvirtError, e:
                self.log.debug("Libvirt Domain Info Failed:")
                self.log.debug(" code is %d" % e.get_error_code())
                self.log.debug(" domain is %d" % e.get_error_domain())
                self.log.debug(" message is %s" % e.get_error_message())
                self.log.debug(" level is %d" % e.get_error_level())
                self.log.debug(" str1 is %s" % e.get_str1())
                self.log.debug(" str2 is %s" % e.get_str2())
                self.log.debug(" str3 is %s" % e.get_str3())
                self.log.debug(" int1 is %d" % e.get_int1())
                self.log.debug(" int2 is %d" % e.get_int2())
                if e.get_error_domain() == libvirt.VIR_FROM_QEMU and (e.get_error_code() in [libvirt.VIR_ERR_NO_DOMAIN, libvirt.VIR_ERR_SYSTEM_ERROR, libvirt.VIR_ERR_OPERATION_FAILED]):
                    break
                else:
                    raise

            count -= 1
            time.sleep(1)

        if count == 0:
            # if we timed out, then let's make sure to take a screenshot.
            screenshot = self.name + "-" + str(time.time()) + ".png"
            self.capture_screenshot(libvirt_dom.XMLDesc(0), screenshot)
            raise OzException.OzException("Timed out waiting for install to finish")

        self.log.info("Install of %s succeeded" % (self.name))

    def wait_for_guest_shutdown(self, libvirt_dom, count=60):
        origcount = count
        while count > 0:
            if count % 10 == 0:
                self.log.debug("Waiting for %s to shutdown, %d/%d" % (self.name, count, origcount))
            try:
                info = libvirt_dom.info()
            except libvirt.libvirtError, e:
                self.log.debug("Libvirt Domain Info Failed:")
                self.log.debug(" code is %d" % e.get_error_code())
                self.log.debug(" domain is %d" % e.get_error_domain())
                self.log.debug(" message is %s" % e.get_error_message())
                self.log.debug(" level is %d" % e.get_error_level())
                self.log.debug(" str1 is %s" % e.get_str1())
                self.log.debug(" str2 is %s" % e.get_str2())
                self.log.debug(" str3 is %s" % e.get_str3())
                self.log.debug(" int1 is %d" % e.get_int1())
                self.log.debug(" int2 is %d" % e.get_int2())
                if e.get_error_domain() == libvirt.VIR_FROM_QEMU and (e.get_error_code() in [libvirt.VIR_ERR_NO_DOMAIN, libvirt.VIR_ERR_SYSTEM_ERROR, libvirt.VIR_ERR_OPERATION_FAILED]):
                    break
                else:
                    raise

            count -= 1
            time.sleep(1)

        return count != 0

    def get_original_media(self, url, output, force_download):
        self.log.info("Fetching the original media")

        response = urllib2.urlopen(url)
        url = response.geturl()
        info = response.info()
        response.close()

        if not info.has_key("Content-Length"):
            raise OzException.OzException("Could not reach destination to fetch boot media")
        content_length = int(info["Content-Length"])
        if content_length == 0:
            raise OzException.OzException("Install media of 0 size detected, something is wrong")

        original_available = False
        if not force_download and os.access(output, os.F_OK):
            if content_length == os.stat(output)[stat.ST_SIZE]:
                original_available = True

        if original_available:
            self.log.info("Original install media available, using cached version")
        else:
            # before fetching everything, make sure that we have enough
            # space on the filesystem to store the data we are about to download
            outdir = os.path.dirname(output)
            self.mkdir_p(outdir)
            devdata = os.statvfs(outdir)
            if (devdata.f_bsize*devdata.f_bavail) < content_length:
                raise OzException.OzException("Not enough room on %s for install media" % (outdir))
            self.log.info("Fetching the original install media from %s" % (url))
            self.last_mb = -1
            def progress(down_total, down_current, up_total, up_current):
                if down_total == 0:
                    return
                current_mb = int(down_current) / 10485760
                if current_mb > self.last_mb or down_current == down_total:
                    self.last_mb = current_mb
                    self.log.debug("%dkB of %dkB" % (down_current/1024, down_total/1024))

            self.outf = open(output, "w")
            def data(buf):
                self.outf.write(buf)

            c = pycurl.Curl()
            c.setopt(c.URL, url)
            c.setopt(c.CONNECTTIMEOUT, 5)
            c.setopt(c.WRITEFUNCTION, data)
            c.setopt(c.NOPROGRESS, 0)
            c.setopt(c.PROGRESSFUNCTION, progress)
            c.perform()
            c.close()
            self.outf.close()

            if os.stat(output)[stat.ST_SIZE] == 0:
                # if we see a zero-sized media after the download, we know
                # something went wrong
                raise OzException.OzException("Media of 0 size downloaded")

    def capture_screenshot(self, xml, filename):
        doc = libxml2.parseMemory(xml, len(xml))
        graphics = doc.xpathEval('/domain/devices/graphics')
        if len(graphics) != 1:
            self.log.error("Could not find the VNC port")
            return

        if graphics[0].prop('type') != 'vnc':
            self.log.error("Graphics type is not VNC, not taking screenshot")
            return

        port = graphics[0].prop('port')

        if port is None:
            self.log.error("Port is not specified, not taking screenshot")
            return

        vnc = "localhost:%s" % (int(port) - 5900)

        try:
            subprocess_check_output(['gvnccapture', vnc, filename])
        except:
            self.log.error("Failed to take screenshot")

    def guestfs_handle_setup(self, libvirt_xml):
        input_doc = libxml2.parseMemory(libvirt_xml, len(libvirt_xml))
        namenode = input_doc.xpathEval('/domain/name')
        if len(namenode) != 1:
            raise OzException.OzException("invalid libvirt XML with no name")
        input_name = namenode[0].getContent()
        disks = input_doc.xpathEval('/domain/devices/disk')
        if len(disks) != 1:
            raise OzException.OzException("oz cannot handle a libvirt domain with more than 1 disk")
        source = disks[0].xpathEval('source')
        if len(source) != 1:
            raise OzException.OzException("invalid <disk> entry without a source")
        input_disk = source[0].prop('file')
        driver = disks[0].xpathEval('driver')
        if len(driver) == 0:
            input_disk_type = 'raw'
        elif len(driver) == 1:
            input_disk_type = driver[0].prop('type')
        else:
            raise OzException.OzException("invalid <disk> entry without a driver")

        for domid in self.libvirt_conn.listDomainsID():
            self.log.debug("DomID: %d" % (domid))
            dom = self.libvirt_conn.lookupByID(domid)
            xml = dom.XMLDesc(0)
            doc = libxml2.parseMemory(xml, len(xml))
            namenode = doc.xpathEval('/domain/name')
            if len(namenode) != 1:
                # hm, odd, a domain without a name?
                raise OzException.OzException("Saw a domain without a name, something weird is going on")
            if input_name == namenode[0].getContent():
                raise OzException.OzException("Cannot setup ICICLE generation on a running guest")
            disks = doc.xpathEval('/domain/devices/disk')
            if len(disks) < 1:
                # odd, a domain without a disk, but don't worry about it
                continue
            for guestdisk in disks:
                for source in guestdisk.xpathEval("source"):
                    # FIXME: this will only work for files; we can make it work
                    # for other things by following something like:
                    # http://git.annexia.org/?p=libguestfs.git;a=blob;f=src/virt.c;h=2c6be3c6a2392ab8242d1f4cee9c0d1445844385;hb=HEAD#l169
                    filename = str(source.prop('file'))
                    if filename == input_disk:
                        raise OzException.OzException("Cannot setup ICICLE generation on a running disk")


        self.log.info("Setting up guestfs handle for %s" % (self.name))
        g = guestfs.GuestFS()

        self.log.debug("Adding disk image %s" % (input_disk))
        # NOTE: we use "add_drive_opts" here so we can specify the type
        # of the diskimage.  Otherwise it might be possible for an attacker
        # to fool libguestfs with a specially-crafted diskimage that looks
        # like a qcow2 disk (thanks to rjones for the tip)
        g.add_drive_opts(input_disk, format=input_disk_type)

        self.log.debug("Launching guestfs")
        g.launch()

        self.log.debug("Inspecting guest OS")
        roots = g.inspect_os()

        if len(roots) == 0:
            raise OzException.OzException("No operating systems found on the disk")

        self.log.debug("Getting mountpoints")
        for root in roots:
            self.log.debug("Root device: %s" % root)

            # the problem here is that the list of mountpoints returned by
            # inspect_get_mountpoints is in no particular order.  So if the
            # diskimage contains /usr and /usr/local on different devices,
            # but /usr/local happened to come first in the listing, the
            # devices would get mapped improperly.  The clever solution here is
            # to sort the mount paths by length; this will ensure that they
            # are mounted in the right order.  Thanks to rjones for the hint,
            # and the example code that comes from the libguestfs.org python
            # example page.
            mps = g.inspect_get_mountpoints(root)
            def compare(a, b):
                if len(a[0]) > len(b[0]):
                    return 1
                elif len(a[0]) == len(b[0]):
                    return 0
                else:
                    return -1
            mps.sort(compare)
            for mp_dev in mps:
                g.mount_options('', mp_dev[1], mp_dev[0])

        return g

    def guestfs_handle_cleanup(self, g_handle):
        self.log.info("Cleaning up guestfs handle for %s" % (self.name))
        self.log.debug("Syncing")
        g_handle.sync()

        self.log.debug("Unmounting all")
        g_handle.umount_all()

        self.log.debug("Killing guestfs subprocess")
        g_handle.kill_subprocess()

    def wait_for_guest_boot(self):
        self.log.info("Waiting for guest %s to boot" % (self.name))

        listen = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        addr = None
        try:
            listen.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listen.bind((self.host_bridge_ip, self.listen_port))
            listen.listen(1)
            subprocess_check_output(["iptables", "-I", "INPUT", "1",
                                     "-p", "tcp", "-m", "tcp",
                                     "-d", self.host_bridge_ip,
                                     "--dport", str(self.listen_port),
                                     "-j", "ACCEPT"])

            try:
                count = 300
                while count > 0:
                    self.log.debug("Waiting for guest %s to boot, %d/300" % (self.name, count))
                    rlist, wlist, xlist = select.select([listen], [], [], 10)
                    if len(rlist) > 0:
                        new_sock, addr = listen.accept()
                        new_sock.close()
                        break
                    count -= 10
            finally:
                try:
                    subprocess_check_output(["iptables", "-D", "INPUT", "1"])
                except:
                    self.log.warn("Failed to delete iptables rule")
        finally:
            listen.close()

        if addr is None:
            raise OzException.OzException("Timed out waiting for domain to boot")

        self.log.debug("IP address of guest is %s" % (addr[0]))

        return addr[0]

    def output_icicle_xml(self, lines):
        doc = libxml2.newDoc("1.0")
        icicle = doc.newChild(None, "icicle", None)
        packages = icicle.newChild(None, "packages", None)

        lines.sort()
        for line in lines:
            if line == "":
                continue
            package = packages.newChild(None, "package", None)
            package.setProp("name", line)

        return doc.serialize(None, 1)

    def mkdir_p(self, path):
        if not os.access(path, os.F_OK):
            os.makedirs(path)

class CDGuest(Guest):
    def __init__(self, name, distro, update, arch, installtype, nicmodel,
                 clockoffset, mousetype, diskbus, config):
        Guest.__init__(self, name, distro, update, arch, nicmodel, clockoffset,
                       mousetype, diskbus, config)

        self.orig_iso = os.path.join(self.data_dir, "isos",
                                     self.distro + self.update + self.arch + "-" + installtype + ".iso")
        self.modified_iso_cache = os.path.join(self.data_dir, "isos",
                                               self.distro + self.update + self.arch + "-" + installtype + "-oz.iso")
        self.output_iso = os.path.join(self.output_dir,
                                       self.name + "-" + installtype + "-oz.iso")
        self.iso_contents = os.path.join(self.data_dir, "isocontent",
                                         self.name + "-" + installtype)

        self.log.debug("Original ISO path: %s" % self.orig_iso)
        self.log.debug("Modified ISO cache: %s" % self.modified_iso_cache)
        self.log.debug("Output ISO path: %s" % self.output_iso)
        self.log.debug("ISO content path: %s" % self.iso_contents)

    def get_original_iso(self, isourl, force_download):
        self.get_original_media(isourl, self.orig_iso, force_download)

    def copy_iso(self):
        self.log.info("Copying ISO contents for modification")
        if os.access(self.iso_contents, os.F_OK):
            shutil.rmtree(self.iso_contents)
        os.makedirs(self.iso_contents)

        self.log.info("Setting up guestfs handle for %s" % (self.name))
        gfs = guestfs.GuestFS()
        self.log.debug("Adding ISO image %s" % (self.orig_iso))
        gfs.add_drive_opts(self.orig_iso, readonly=1, format='raw')
        self.log.debug("Launching guestfs")
        gfs.launch()
        try:
            self.log.debug("Mounting ISO")
            gfs.mount_options('ro', "/dev/sda", "/")

            self.log.debug("Checking if there is enough space on the filesystem")
            isostat = gfs.statvfs("/")
            outputstat = os.statvfs(self.iso_contents)
            if (outputstat.f_bsize*outputstat.f_bavail) < (isostat['blocks']*isostat['bsize']):
                raise OzException.OzException("Not enough room on %s to extract install media" % (self.iso_contents))

            self.log.debug("Extracting ISO contents")
            current = os.getcwd()
            os.chdir(self.iso_contents)
            try:
                rd,wr = os.pipe()

                try:
                    # NOTE: it is very, very important that we use temporary
                    # files for collecting stdout and stderr here.  There is a
                    # nasty bug in python subprocess; if your process produces
                    # more than 64k of data on an fd that is using
                    # subprocess.PIPE, the whole thing will hang. To avoid
                    # this, we use temporary fds to capture the data
                    stdouttmp = tempfile.TemporaryFile()
                    stderrtmp = tempfile.TemporaryFile()

                    try:
                        tar = subprocess.Popen(["tar", "-x", "-v"], stdin=rd,
                                               stdout=stdouttmp,
                                               stderr=stderrtmp)
                        try:
                            gfs.tar_out("/", "/dev/fd/%d" % wr)
                        except:
                            # we need this here if gfs.tar_out throws an
                            # exception.  In that case, we need to manually
                            # kill off the tar process and re-raise the
                            # exception, otherwise we hang forever
                            tar.kill()
                            raise

                        # FIXME: we really should check tar.poll() here to get
                        # the return code, and print out stdout and stderr if
                        # we fail.  This will make debugging problems easier
                    finally:
                        stdouttmp.close()
                        stderrtmp.close()
                finally:
                    os.close(rd)
                    os.close(wr)
            finally:
                os.chdir(current)
        finally:
            gfs.sync()
            gfs.umount_all()
            gfs.kill_subprocess()

    def get_primary_volume_descriptor(self, cdfile):
        cdfile = open(cdfile, "r")

        # check out the primary volume descriptor to make sure it is sane
        cdfile.seek(16*2048)
        fmt = "=B5sBB32s32sQLL32sHHHH"
        (desc_type, identifier, version, unused1, system_identifier, volume_identifier, unused2, space_size_le, space_size_be, unused3, set_size_le, set_size_be, seqnum_le, seqnum_be) = struct.unpack(fmt, cdfile.read(struct.calcsize(fmt)))

        if desc_type != 0x1:
            raise OzException.OzException("Invalid primary volume descriptor")
        if identifier != "CD001":
            raise OzException.OzException("invalid CD isoIdentification")
        if unused1 != 0x0:
            raise OzException.OzException("data in unused field")
        if unused2 != 0x0:
            raise OzException.OzException("data in 2nd unused field")

        return volume_identifier

    def geteltorito(self, cdfile, outfile):
        get_primary_volume_descriptor(cdfile)

        cdfile = open(cdfile, "r")

        # the 17th sector contains the boot specification and the offset of the
        # boot sector
        cdfile.seek(17*2048)

        # NOTE: With "native" alignment (the default for struct), there is
        # some padding that happens that causes the unpacking to fail.
        # Instead we force "standard" alignment, which has no padding
        fmt = "=B5sB23s41sI"
        (boot, isoIdent, version, toritoSpec, unused, bootP) = struct.unpack(fmt, cdfile.read(struct.calcsize(fmt)))
        if boot != 0x0:
            raise OzException.OzException("invalid CD boot sector")
        if version != 0x1:
            raise OzException.OzException("invalid CD version")
        if isoIdent != "CD001":
            raise OzException.OzException("invalid CD isoIdentification")
        if toritoSpec != "EL TORITO SPECIFICATION":
            raise OzException.OzException("invalid CD torito specification")

        # OK, this looks like a bootable CD.  Seek to the boot sector, and
        # look for the header, 0x55, and 0xaa in the first 32 bytes
        cdfile.seek(bootP*2048)
        fmt = "=BBH24sHBB"
        bootdata = cdfile.read(struct.calcsize(fmt))
        (header, platform, unused, manu, unused2, five, aa) = struct.unpack(fmt, bootdata)
        if header != 0x1:
            raise OzException.OzException("invalid CD boot sector header")
        if platform != 0x0 and platform != 0x1 and platform != 0x2:
            raise OzException.OzException("invalid CD boot sector platform")
        if unused != 0x0:
            raise OzException.OzException("invalid CD unused boot sector field")
        if five != 0x55 or aa != 0xaa:
            raise OzException.OzException("invalid CD boot sector footer")

        def checksum(data):
            s = 0
            for i in range(0, len(data), 2):
                w = ord(data[i]) + (ord(data[i+1]) << 8)
                s = numpy.uint16(numpy.uint16(s) + numpy.uint16(w))
            return s

        csum = checksum(bootdata)
        if csum != 0:
            raise OzException.OzException("invalid CD checksum: expected 0, saw %d" % (csum))

        # OK, everything so far has checked out.  Read the default/initial
        # boot entry
        cdfile.seek(bootP*2048+32)
        fmt = "=BBHBBHIB"
        (boot, media, loadsegment, systemtype, unused, scount, imgstart, unused2) = struct.unpack(fmt, cdfile.read(struct.calcsize(fmt)))

        if boot != 0x88:
            raise OzException.OzException("invalid CD initial boot indicator")
        if unused != 0x0 or unused2 != 0x0:
            raise OzException.OzException("invalid CD initial boot unused field")

        if media == 0 or media == 4:
            count = scount
        elif media == 1:
            # 1.2MB floppy in sectors
            count = 1200*1024/512
        elif media == 2:
            # 1.44MB floppy in sectors
            count = 1440*1024/512
        elif media == 3:
            # 2.88MB floppy in sectors
            count = 2880*1024/512
        else:
            raise OzException.OzException("invalid CD media type")

        # finally, seek to "imgstart", and read "count" sectors, which
        # contains the boot image
        cdfile.seek(imgstart*2048)

        # The eltorito specification section 2.5 says:
        #
        # Sector Count. This is the number of virtual/emulated sectors the
        # system will store at Load Segment during the initial boot
        # procedure.
        #
        # and then Section 1.5 says:
        #
        # Virtual Disk - A series of sectors on the CD which INT 13 presents
        # to the system as a drive with 200 byte virtual sectors. There
        # are 4 virtual sectors found in each sector on a CD.
        #
        # (note that the bytes above are in hex).  So we read count*512
        eltoritodata = cdfile.read(count*512)
        cdfile.close()

        out = open(outfile, "w")
        out.write(eltoritodata)
        out.close()

    def install(self, timeout=None):
        self.log.info("Running install for %s" % (self.name))
        xml = self.generate_xml("cdrom")
        dom = self.libvirt_conn.createXML(xml, 0)

        if timeout is None:
            timeout = 1200

        self.wait_for_install_finish(dom, timeout)

        if self.cache_jeos:
            self.log.info("Caching JEOS")
            self.mkdir_p(self.jeos_cache_dir)
            ozutil.copyfile_sparse(self.diskimage, self.jeos_filename)

        return self.generate_xml("hd", want_install_disk=False)

    def cleanup_iso(self):
        self.log.info("Cleaning up old ISO data")
        shutil.rmtree(self.iso_contents)

    def cleanup_install(self):
        self.log.info("Cleaning up after install")
        os.unlink(self.output_iso)
        self.log.debug("Removed modified ISO")
        if not self.cache_original_media:
            os.unlink(self.orig_iso)

class FDGuest(Guest):
    def __init__(self, name, distro, update, arch, nicmodel, clockoffset,
                 mousetype, diskbus, config):
        Guest.__init__(self, name, distro, update, arch, nicmodel, clockoffset,
                       mousetype, diskbus, config)
        self.orig_floppy = os.path.join(self.data_dir, "floppies",
                                        self.distro + self.update + self.arch + ".img")
        self.modified_floppy_cache = os.path.join(self.data_dir, "floppies",
                                                  self.distro + self.update + self.arch + "-oz.img")
        self.output_floppy = os.path.join(self.output_dir, self.name + "-oz.img")
        self.floppy_contents = os.path.join(self.data_dir, "floppycontent", self.name)

        self.log.debug("Original floppy path: %s" % self.orig_floppy)
        self.log.debug("Modified floppy cache: %s" % self.modified_floppy_cache)
        self.log.debug("Output floppy path: %s" % self.output_floppy)
        self.log.debug("Floppy content path: %s" % self.floppy_contents)

    def get_original_floppy(self, floppyurl, force_download):
        self.get_original_media(floppyurl, self.orig_floppy, force_download)

    def copy_floppy(self):
        self.log.info("Copying floppy contents for modification")
        shutil.copyfile(self.orig_floppy, self.output_floppy)

    def install(self, timeout=None):
        self.log.info("Running install for %s" % (self.name))
        xml = self.generate_xml("fd")
        dom = self.libvirt_conn.createXML(xml, 0)

        if timeout is None:
            timeout = 1200

        self.wait_for_install_finish(dom, timeout)

        if self.cache_jeos:
            self.log.info("Caching JEOS")
            self.mkdir_p(self.jeos_cache_dir)
            ozutil.copyfile_sparse(self.diskimage, self.jeos_filename)

        return self.generate_xml("hd", want_install_disk=False)

    def cleanup_floppy(self):
        self.log.info("Cleaning up floppy data")
        shutil.rmtree(self.floppy_contents)

    def cleanup_install(self):
        self.log.info("Cleaning up after install")
        os.unlink(self.output_floppy)
        self.log.debug("Removed modified floppy")
        if not self.cache_original_media:
            os.unlink(self.orig_floppy)
