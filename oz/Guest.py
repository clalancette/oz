# Copyright (C) 2010  Chris Lalancette <clalance@redhat.com>

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
import xml.dom.minidom
import pycurl
import sys
import urllib2
import re
import stat
import ozutil
import libxml2
import logging
import random
import guestfs
import socket
import select
import tarfile
import struct
import numpy

class ProcessError(Exception):
    """This exception is raised when a process run by
    Guest.subprocess_check_output returns a non-zero exit status.  The exit
    status will be stored in the returncode attribute
    """
    def __init__(self, returncode, cmd, output=None):
        self.returncode = returncode
        self.cmd = cmd
        self.output = output
    def __str__(self):
        return "'%s' failed(%d): %s" % (self.cmd, self.returncode, self.output)

# NOTE: python 2.7 already defines subprocess.capture_output, but I can't
# depend on that yet.  So write my own
def subprocess_check_output(*popenargs, **kwargs):
    if 'stdout' in kwargs:
        raise ValueError('stdout argument not allowed, it will be overridden.')

    ozutil.executable_exists(popenargs[0][0])

    process = subprocess.Popen(stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, *popenargs, **kwargs)
    output, unused_err = process.communicate()
    retcode = process.poll()
    if retcode:
        cmd = ' '.join(*popenargs)
        raise ProcessError(retcode, cmd, output=output)
    return output

class NullHandler(logging.Handler):
    def emit(self, record):
        pass

class Guest(object):
    def __init__(self, distro, update, arch, nicmodel, clockoffset, mousetype,
                 diskbus, config):
        if arch != "i386" and arch != "x86_64":
            raise Exception, "Unsupported guest arch " + arch
        self.log = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))
        self.uuid = uuid.uuid4()
        mac = [0x52, 0x54, 0x00, random.randint(0x00, 0xff),
               random.randint(0x00, 0xff), random.randint(0x00, 0xff)]
        self.macaddr = ':'.join(map(lambda x:"%02x" % x, mac))
        self.distro = distro
        self.update = update
        self.arch = arch
        self.name = self.distro + self.update + self.arch

        if config is not None and config.has_section('paths') and config.has_option('paths', 'output_dir'):
            self.output_dir = config.get('paths', 'output_dir')
        else:
            self.output_dir = "/var/lib/libvirt/images"

        if config is not None and config.has_section('paths') and config.has_option('paths', 'data_dir'):
            self.data_dir = config.get('paths', 'data_dir')
        else:
            self.data_dir = "/var/lib/oz"

        self.diskimage = self.output_dir + "/" + self.name + ".dsk"
        self.cdl_tmp = self.data_dir + "/cdltmp/" + self.name
        self.listen_port = random.randrange(1024, 65535)
        self.libvirt_conn = libvirt.open("qemu:///system")

        # we have to make sure that the private libvirt bridge is available
        self.host_bridge_ip = None
        for netname in self.libvirt_conn.listNetworks():
            network = self.libvirt_conn.networkLookupByName(netname)
            if network.bridgeName() == 'virbr0':
                xml = network.XMLDesc(0)
                doc = libxml2.parseMemory(xml, len(xml))
                ip = doc.xpathEval('/network/ip')
                if len(ip) != 1:
                    raise Exception, "Failed to find host IP address for virbr0"
                self.host_bridge_ip = ip[0].prop('address')
                break
        if self.host_bridge_ip is None:
            raise Exception, "Default libvirt network (virbr0) does not exist, install cannot continue"

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
            raise Exception, "Unknown diskbus type " + diskbus

        self.log.debug("Name: %s, UUID: %s, MAC: %s, distro: %s" % (self.name, self.uuid, self.macaddr, self.distro))
        self.log.debug("update: %s, arch: %s, diskimage: %s" % (self.update, self.arch, self.diskimage))
        self.log.debug("host IP: %s, nicmodel: %s, clockoffset: %s" % (self.host_bridge_ip, self.nicmodel, self.clockoffset))
        self.log.debug("mousetype: %s, disk_bus: %s, disk_dev: %s" % (self.mousetype, self.disk_bus, self.disk_dev))
        self.log.debug("cdltmp: %s, listen_port: %d" % (self.cdl_tmp, self.listen_port))

    def cleanup_old_guest(self, delete_disk=True):
        def handler(ctxt, err):
            pass
        libvirt.registerErrorHandler(handler, 'context')
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
        libvirt.registerErrorHandler(None, None)

        if delete_disk and os.access(self.diskimage, os.F_OK):
            os.unlink(self.diskimage)

    def targetDev(self, doc, devicetype, path, bus):
        installNode = doc.createElement("disk")
        installNode.setAttribute("type", "file")
        installNode.setAttribute("device", devicetype)
        sourceInstallNode = doc.createElement("source")
        sourceInstallNode.setAttribute("file", path)
        installNode.appendChild(sourceInstallNode)
        targetInstallNode = doc.createElement("target")
        targetInstallNode.setAttribute("dev", bus)
        installNode.appendChild(targetInstallNode)
        return installNode

    def generate_define_xml(self, bootdev, want_install_disk=True):
        self.log.info("Generate/define XML for guest %s with bootdev %s" % (self.name, bootdev))

        # create top-level domain element
        doc = xml.dom.minidom.Document()
        domain = doc.createElement("domain")
        domain.setAttribute("type", "kvm")
        doc.appendChild(domain)

        # create name element
        nameNode = doc.createElement("name")
        nameNode.appendChild(doc.createTextNode(self.name))
        domain.appendChild(nameNode)

        # create memory nodes
        memoryNode = doc.createElement("memory")
        currentMemoryNode = doc.createElement("currentMemory")
        memoryNode.appendChild(doc.createTextNode(str(1024 * 1024)))
        currentMemoryNode.appendChild(doc.createTextNode(str(1024 * 1024)))
        domain.appendChild(memoryNode)
        domain.appendChild(currentMemoryNode)

        # create uuid
        uuidNode = doc.createElement("uuid")
        uuidNode.appendChild(doc.createTextNode(str(self.uuid)))
        domain.appendChild(uuidNode)

        # clock offset
        offsetNode = doc.createElement("clock")
        offsetNode.setAttribute("offset", self.clockoffset)
        domain.appendChild(offsetNode)

        # create vcpu
        vcpusNode = doc.createElement("vcpu")
        vcpusNode.appendChild(doc.createTextNode(str(1)))
        domain.appendChild(vcpusNode)

        # create features
        featuresNode = doc.createElement("features")
        acpiNode = doc.createElement("acpi")
        apicNode = doc.createElement("apic")
        paeNode = doc.createElement("pae")
        featuresNode.appendChild(acpiNode)
        featuresNode.appendChild(apicNode)
        featuresNode.appendChild(paeNode)
        domain.appendChild(featuresNode)

        # create os
        osNode = doc.createElement("os")
        typeNode = doc.createElement("type")
        typeNode.appendChild(doc.createTextNode("hvm"))
        osNode.appendChild(typeNode)
        bootNode = doc.createElement("boot")
        bootNode.setAttribute("dev", bootdev)
        osNode.appendChild(bootNode)
        domain.appendChild(osNode)

        # create poweroff, reboot, crash nodes
        poweroffNode = doc.createElement("on_poweroff")
        rebootNode = doc.createElement("on_reboot")
        crashNode = doc.createElement("on_crash")
        poweroffNode.appendChild(doc.createTextNode("destroy"))
        rebootNode.appendChild(doc.createTextNode("destroy"))
        crashNode.appendChild(doc.createTextNode("destroy"))
        domain.appendChild(poweroffNode)
        domain.appendChild(rebootNode)
        domain.appendChild(crashNode)

        # create devices section
        devicesNode = doc.createElement("devices")
        # console
        consoleNode = doc.createElement("console")
        consoleNode.setAttribute("device", "pty")
        devicesNode.appendChild(consoleNode)
        # graphics
        graphicsNode = doc.createElement("graphics")
        graphicsNode.setAttribute("type", "vnc")
        graphicsNode.setAttribute("port", "-1")
        devicesNode.appendChild(graphicsNode)
        # network
        interfaceNode = doc.createElement("interface")
        interfaceNode.setAttribute("type", "bridge")
        sourceNode = doc.createElement("source")
        sourceNode.setAttribute("bridge", "virbr0")
        interfaceNode.appendChild(sourceNode)
        macNode = doc.createElement("mac")
        macNode.setAttribute("address", self.macaddr)
        interfaceNode.appendChild(macNode)
        modelNode = doc.createElement("model")
        modelNode.setAttribute("type", self.nicmodel)
        interfaceNode.appendChild(modelNode)
        devicesNode.appendChild(interfaceNode)
        # input
        inputNode = doc.createElement("input")
        if self.mousetype == "ps2":
            inputNode.setAttribute("type", "mouse")
            inputNode.setAttribute("bus", "ps2")
        elif self.mousetype == "usb":
            inputNode.setAttribute("type", "tablet")
            inputNode.setAttribute("bus", "usb")
        devicesNode.appendChild(inputNode)
        # console
        consoleNode = doc.createElement("console")
        consoleNode.setAttribute("type", "pty")
        targetConsoleNode = doc.createElement("target")
        targetConsoleNode.setAttribute("port", "0")
        consoleNode.appendChild(targetConsoleNode)
        devicesNode.appendChild(consoleNode)
        # boot disk
        diskNode = doc.createElement("disk")
        diskNode.setAttribute("type", "file")
        diskNode.setAttribute("device", "disk")
        targetNode = doc.createElement("target")
        targetNode.setAttribute("dev", self.disk_dev)
        targetNode.setAttribute("bus", self.disk_bus)
        diskNode.appendChild(targetNode)
        sourceDiskNode = doc.createElement("source")
        sourceDiskNode.setAttribute("file", self.diskimage)
        diskNode.appendChild(sourceDiskNode)
        devicesNode.appendChild(diskNode)
        # install disk (cdrom or floppy)
        if want_install_disk:
            if hasattr(self, "output_iso"):
                devicesNode.appendChild(self.targetDev(doc, "cdrom", self.output_iso, "hdc"))
            if hasattr(self, "output_floppy"):
                devicesNode.appendChild(self.targetDev(doc, "floppy", self.output_floppy, "fda"))
        domain.appendChild(devicesNode)

        self.log.debug("Generated XML:\n%s" % (doc.toprettyxml()))
        self.libvirt_dom = self.libvirt_conn.defineXML(doc.toxml())

        return doc.toxml()

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

    def wait_for_install_finish(self, count):
        origcount = count
        failed = False
        while count > 0:
            try:
                if count % 10 == 0:
                    self.log.debug("Waiting for %s to finish installing, %d/%d" % (self.name, count, origcount))
                info = self.libvirt_dom.info()
                if info[0] == libvirt.VIR_DOMAIN_SHUTOFF:
                    # the domain is now shutoff, so get out of here
                    break
                elif info[0] != libvirt.VIR_DOMAIN_RUNNING and info[0] != libvirt.VIR_DOMAIN_BLOCKED:
                    # the domain isn't running or blocked; something bad
                    # happened, so get out of here and report the error
                    failed = True
                    break
                count -= 1
            except:
                pass
            time.sleep(1)

        if failed or count == 0:
            # if we timed out, then let's make sure to take a screenshot.
            # FIXME: where should we put this screenshot?
            screenshot = self.name + "-" + str(time.time()) + ".png"
            self.capture_screenshot(self.libvirt_dom.XMLDesc(0), screenshot)
            if failed:
                raise Exception, "Failed installation, domain went to state %d" % (info[0])
            else:
                raise Exception, "Timed out waiting for install to finish"

        self.log.info("Install of %s succeeded" % (self.name))

    def get_original_media(self, url, output, force_download):
        original_available = False

        request = urllib2.Request(url)
        try:
            response = urllib2.urlopen(request)
            url = response.geturl()
            if not force_download and os.access(output, os.F_OK):
                content_length = int(response.info()["Content-Length"])
                if content_length == os.stat(output)[stat.ST_SIZE]:
                    original_available = True
            response.close()
        except urllib2.URLError, e:
            raise e
        except:
            pass

        if original_available:
            self.log.info("Original install media available, using cached version")
        else:
            self.log.info("Fetching the original install media from %s" % (url))
            self.last_mb = -1
            def progress(down_total, down_current, up_total, up_current):
                if down_total == 0:
                    return
                current_mb = int(down_current) / 10485760
                if current_mb > self.last_mb or down_current == down_total:
                    self.last_mb = current_mb
                    self.log.debug("%dkB of %dkB" % (down_current/1024, down_total/1024))

            if not os.access(os.path.dirname(output), os.F_OK):
                os.makedirs(os.path.dirname(output))
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
                raise Exception, "Media of 0 size downloaded"

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

        # we don't use subprocess_check_output here because if this fails,
        # we don't want to raise an exception, just print an error
        ret = subprocess.call(['gvnccapture', vnc, filename], stdout=open('/dev/null', 'w'), stderr=subprocess.STDOUT)
        if ret != 0:
            self.log.error("Failed to take screenshot")

    def guestfs_handle_setup(self, libvirt_xml):
        input_doc = libxml2.parseMemory(libvirt_xml, len(libvirt_xml))
        namenode = input_doc.xpathEval('/domain/name')
        if len(namenode) != 1:
            raise Exception, "invalid libvirt XML with no name"
        input_name = namenode[0].getContent()
        disks = input_doc.xpathEval('/domain/devices/disk/source')
        if len(disks) != 1:
            raise Exception, "oz cannot handle a libvirt domain with more than 1 disk"
        input_disk = disks[0].prop('file')

        for domid in self.libvirt_conn.listDomainsID():
            self.log.debug("DomID: %d" % (domid))
            dom = self.libvirt_conn.lookupByID(domid)
            xml = dom.XMLDesc(0)
            doc = libxml2.parseMemory(xml, len(xml))
            namenode = doc.xpathEval('/domain/name')
            if len(namenode) != 1:
                # hm, odd, a domain without a name?
                raise Exception, "Saw a domain without a name, something weird is going on"
            if input_name == namenode[0].getContent():
                raise Exception, "Cannot setup CDL generation on a running guest"
            disks = doc.xpathEval('/domain/devices/disk')
            if len(disks) < 1:
                # odd, a domain without a disk, but don't worry about it
                continue
            for guestdisk in disks:
                for source in guestdisk.xpathEval("source"):
                    filename = str(source.prop('file'))
                    if filename == input_disk:
                        raise Exception, "Cannot setup CDL generation on a running disk"


        self.log.info("Setting up guestfs handle for %s" % (self.name))
        g = guestfs.GuestFS()

        self.log.debug("Adding disk image %s" % (input_disk))
        g.add_drive(input_disk)

        self.log.debug("Launching guestfs")
        g.launch()

        self.log.debug("Inspecting guest OS")
        os = g.inspect_os()

        self.log.debug("Getting mountpoints")
        mountpoints = g.inspect_get_mountpoints(os[0])

        self.log.debug("Mounting /")
        for point in mountpoints:
            if point[0] == '/':
                g.mount(point[1], '/')
                break

        self.log.debug("Mount other filesystems")
        for point in mountpoints:
            if point[0] != '/':
                g.mount(point[1], point[0])

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
        self.log.info("Listening on %d for %s to boot" % (self.listen_port, self.name))

        listen = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listen.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listen.bind((self.host_bridge_ip, self.listen_port))
        listen.listen(1)
        subprocess_check_output(["iptables", "-I", "INPUT", "1", "-p", "tcp",
                                 "-m", "tcp", "-d", self.host_bridge_ip,
                                 "--dport", str(self.listen_port),
                                 "-j", "ACCEPT"])

        try:
            rlist, wlist, xlist = select.select([listen], [], [], 300)
        finally:
            subprocess.call(["iptables", "-D", "INPUT", "1"])
        if len(rlist) == 0:
            raise Exception, "Timed out waiting for domain to boot"
        new_sock, addr = listen.accept()
        new_sock.close()
        listen.close()

        self.log.debug("IP address of guest is %s" % (addr[0]))

        return addr[0]

    def output_cdl_xml(self, lines, services):
        doc = xml.dom.minidom.Document()
        cdl = doc.createElement("cdl")
        doc.appendChild(cdl)

        tmp = xml.dom.minidom.parseString(services)
        cdl.appendChild(tmp.documentElement)

        packagesNode = doc.createElement("packages")
        cdl.appendChild(packagesNode)

        for line in lines:
            if line == "":
                continue
            packageNode = doc.createElement("package")
            packageNode.setAttribute("name", line)
            packagesNode.appendChild(packageNode)

        return doc.toxml()

class CDGuest(Guest):
    def __init__(self, distro, update, arch, nicmodel, clockoffset, mousetype,
                 diskbus, config):
        Guest.__init__(self, distro, update, arch, nicmodel, clockoffset, mousetype, diskbus, config)
        # FIXME: now that we have both "iso" and "url" type installs, it
        # might behoove us to encode this into orig_iso.  Otherwise, when you
        # switch between them on the same OS, you continually download the
        # "net" install one vs. the full ISO DVD.
        self.orig_iso = self.data_dir + "/isos/" + self.name + ".iso"
        self.output_iso = self.output_dir + "/" + self.name + "-oz.iso"
        self.iso_contents = self.data_dir + "/isocontent/" + self.name

    def get_original_iso(self, isourl, force_download):
        return self.get_original_media(isourl, self.orig_iso, force_download)

    def copy_iso(self):
        self.log.info("Copying ISO contents for modification")
        if os.access(self.iso_contents, os.F_OK):
            shutil.rmtree(self.iso_contents)
        os.makedirs(self.iso_contents)

        tarout = self.iso_contents + "/data.tar"

        self.log.info("Setting up guestfs handle for %s" % (self.name))
        gfs = guestfs.GuestFS()
        self.log.debug("Adding ISO image %s" % (self.orig_iso))
        gfs.add_drive(self.orig_iso)
        self.log.debug("Launching guestfs")
        gfs.launch()
        self.log.debug("Mounting ISO")
        gfs.mount("/dev/sda", "/")
        self.log.debug("Getting data from ISO onto %s" % (tarout))
        gfs.tar_out("/", tarout)

        self.log.debug("Cleaning up guestfs process")
        gfs.sync()
        gfs.umount_all()
        gfs.kill_subprocess()

        self.log.debug("Extracting tarball")
        tar = tarfile.open(tarout)

        # FIXME: the documentation for extractall says that this is potentially
        # dangerous with random data.  In particular, files that start with /
        # or contain .. may cause problems.  We'll need to do some validation
        # here
        tar.extractall(path=self.iso_contents)

        self.log.debug("Removing tarball")
        os.unlink(tarout)

    def geteltorito(self, cdfile, outfile):
        cdfile = open(cdfile, "r")

        # the 17th sector contains the boot specification, and also contains the
        # offset of the "boot" sector
        cdfile.seek(17*2048)

        # NOTE: With "native" alignment (the default for struct), there is
        # some padding that happens that causes the unpacking to fail.  Instead
        # we force "standard" alignment, which really has no constraints
        fmt = "=B5sB23s41sI"
        spec = cdfile.read(struct.calcsize(fmt))
        (boot, isoIdent, version, toritoSpec, unused, bootP) = struct.unpack(fmt, spec)
        if boot != 0x0:
            raise Exception, "invalid boot"
        if version != 0x1:
            raise Exception, "invalid version"
        if isoIdent != "CD001" or toritoSpec != "EL TORITO SPECIFICATION":
            raise Exception, "isoIdentification not correct"

        # OK, this looks like a CD.  Seek to the boot sector, and look for the
        # header, 0x55, and 0xaa in the first 32 bytes
        cdfile.seek(bootP*2048)
        fmt = "=BBH24sHBB"
        bootdata = cdfile.read(struct.calcsize(fmt))
        (header, platform, unused, manu, unused2, five, aa) = struct.unpack(fmt, bootdata)
        if header != 0x1:
            raise Exception, "invalid header"
        if platform != 0x0 and platform != 0x1 and platform != 0x2:
            raise Exception, "invalid platform"
        if unused != 0x0:
            raise Exception, "invalid unused boot sector field"
        if five != 0x55 or aa != 0xaa:
            raise Exception, "invalid footer"

        def checksum(data):
            s = 0
            for i in range(0, len(data), 2):
                w = ord(data[i]) + (ord(data[i+1]) << 8)
                s = numpy.uint16(numpy.uint16(s) + numpy.uint16(w))
            return s

        if checksum(bootdata) != 0:
            raise Exception, "invalid checksum"

        # OK, everything so far has checked out.  Read the default/initial boot
        # entry
        cdfile.seek(bootP*2048+32)
        fmt = "=BBHBBHIB"
        defaultentry = cdfile.read(struct.calcsize(fmt))
        (boot, media, loadsegment, systemtype, unused, scount, imgstart, unused2) = struct.unpack(fmt, defaultentry)

        if boot != 0x88:
            raise Exception, "invalid boot indicator"
        if unused != 0x0 or unused2 != 0x0:
            raise Exception, "invalid unused initial boot field"

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
            raise Exception, "invalid media type"

        # finally, seek to "imgstart", and read "count" sectors, which contains
        # the boot image
        cdfile.seek(imgstart*2048)

        # The eltorito specification section 2.5 says:
        #
        # Sector Count. This is the number of virtual/emulated sectors the
        # system will store at Load Segment during the initial boot procedure.
        #
        # and then Section 1.5 says:
        #
        # Virtual Disk - A series of sectors on the CD which INT 13 presents
        # to the system as a drive with 200 byte virtual sectors. There are 4
        # virtual sectors found in each sector on a CD.
        #
        # (note that the bytes above are in hex).  So we read count*512
        eltoritodata = cdfile.read(count*512)
        cdfile.close()

        out = open(outfile, "w")
        out.write(eltoritodata)
        out.close()

    def install(self):
        self.log.info("Running install for %s" % (self.name))
        self.generate_define_xml("cdrom")
        self.libvirt_dom.create()

        self.wait_for_install_finish(1200)

        return self.generate_define_xml("hd", want_install_disk=False)

    def cleanup_iso(self):
        self.log.info("Cleaning up old ISO data")
        shutil.rmtree(self.iso_contents)

    def cleanup_install(self):
        self.log.info("Cleaning up modified ISO")
        os.unlink(self.output_iso)

class FDGuest(Guest):
    def __init__(self, distro, update, arch, nicmodel, clockoffset, mousetype,
                 diskbus, config):
        Guest.__init__(self, distro, update, arch, nicmodel, clockoffset, mousetype, diskbus, config)
        self.orig_floppy = self.data_dir + "/floppies/" + self.name + ".img"
        self.output_floppy = self.output_dir + "/" + self.name + "-oz.img"
        self.floppy_contents = self.data_dir + "/floppycontent/" + self.name

    def get_original_floppy(self, floppyurl, force_download):
        return self.get_original_media(floppyurl, self.orig_floppy, force_download)

    def copy_floppy(self):
        self.log.info("Copying floppy contents for modification")
        shutil.copyfile(self.orig_floppy, self.output_floppy)

    def install(self):
        self.log.info("Running install for %s" % (self.name))
        self.generate_define_xml("fd")
        self.libvirt_dom.create()

        self.wait_for_install_finish(1200)

        return self.generate_define_xml("hd", want_install_disk=False)

    def cleanup_floppy(self):
        self.log.info("Cleaning up floppy data")
        shutil.rmtree(self.floppy_contents)

    def cleanup_install(self):
        self.log.info("Cleaning up modified floppy")
        os.unlink(self.output_floppy)
