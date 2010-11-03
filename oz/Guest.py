import uuid
import virtinst.util
import libvirt
import os
import subprocess
import shutil
import time
import xml.dom.minidom
import pycurl
import sys
import urllib
import re
import stat
import urlparse
import httplib
import ozutil
import libxml2
import logging

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
    process = subprocess.Popen(stdout=subprocess.PIPE, stderr=subprocess.STDOUT, *popenargs, **kwargs)
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
    def __init__(self, distro, update, arch, macaddr, nicmodel, clockoffset,
                 mousetype, diskbus):
        if arch != "i386" and arch != "x86_64":
            raise Exception, "Unsupported guest arch " + arch
        self.log = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))
        self.uuid = uuid.uuid4()
        self.macaddr = macaddr
        if self.macaddr is None:
            self.macaddr = virtinst.util.randomMAC()
        self.distro = distro
        self.update = update
        self.arch = arch
        self.name = self.distro + self.update + self.arch
        self.diskimage = "/var/lib/libvirt/images/" + self.name + ".dsk"
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
                    raise Exception, "Failed to find host IP address"
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

    def cleanup_old_guest(self):
        def handler(ctxt, err):
            pass
        libvirt.registerErrorHandler(handler, 'context')
        self.log.info("Cleaning up old guest named %s" % (self.name))
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
        if os.access(self.diskimage, os.F_OK):
            os.unlink(self.diskimage)

    def targetDev(self, doc, type, path, bus):
        installNode = doc.createElement("disk")
        installNode.setAttribute("type", "file")
        installNode.setAttribute("device", type)
        sourceInstallNode = doc.createElement("source")
        sourceInstallNode.setAttribute("file", path)
        installNode.appendChild(sourceInstallNode)
        targetInstallNode = doc.createElement("target")
        targetInstallNode.setAttribute("dev", bus)
        installNode.appendChild(targetInstallNode)
        return installNode

    def generate_define_xml(self, bootdev):
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
        arch = self.arch
        if self.arch == "i386":
            arch = "i686"
        osNode = doc.createElement("os")
        typeNode = doc.createElement("type")
        typeNode.setAttribute("arch", arch)
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
        if hasattr(self, "output_iso"):
            devicesNode.appendChild(self.targetDev(doc, "cdrom", self.output_iso, "hdc"))
        if hasattr(self, "output_floppy"):
            devicesNode.appendChild(self.targetDev(doc, "floppy", self.output_floppy, "fda"))
        domain.appendChild(devicesNode)

        self.log.debug("Generated XML:\n%s" % (doc.toxml()))

        self.libvirt_dom = self.libvirt_conn.defineXML(doc.toxml())

    def generate_blank_diskimage(self, size=10):
        self.log.info("Generating %dGB blank diskimage for %s" % (size, self.name))
        f = open(self.diskimage, "w")
        # 10 GB disk image by default
        f.truncate(size * 1024 * 1024 * 1024)
        f.close()

    def generate_diskimage(self, size=10):
        self.log.info("Generating %dGB diskimage with fake partition for %s" % (size, self.name))
        f = open(self.diskimage, "w")
        f.seek(0x1bf)
        f.write("\x01\x01\x00\x82\xfe\x3f\x7c\x3f\x00\x00\x00\xfe\xa3\x1e")
        f.seek(0x1fe)
        f.write("\x55\xaa")
        f.seek(size * 1024 * 1024 * 1024)
        f.write("\x00")
        f.close()

    def wait_for_install_finish(self, count):
        lastlen = 0
        origcount = count
        while count > 0:
            try:
                if count % 10 == 0:
                    self.log.info("Waiting for %s to finish installing, %d/%d" % (self.name, count, origcount))
                info = self.libvirt_dom.info()
                if info[0] != libvirt.VIR_DOMAIN_RUNNING and info[0] != libvirt.VIR_DOMAIN_BLOCKED:
                    break
                count -= 1
            except:
                pass
            time.sleep(1)

        if count == 0:
            # if we timed out, then let's make sure to take a screenshot.
            screenshot = self.name + "-" + str(time.time()) + ".png"
            self.capture_screenshot(self.libvirt_dom.XMLDesc(0), screenshot)
            raise Exception, "Timed out waiting for install to finish"

    def get_original_media(self, url, output):
        original_available = False
        if os.access(output, os.F_OK):
            for header in urllib.urlopen(url).headers.headers:
                if re.match("Content-Length:", header):
                    if int(header.split()[1]) == os.stat(output)[stat.ST_SIZE]:
                        original_available = True
                    break

        if original_available:
            self.log.info("Original install media available, using cached version")
        else:
            self.log.info("Fetching the original install media from %s" % (url))
            def progress(down_total, down_current, up_total, up_current):
                self.log.info("%dkB of %dkB" % (down_current/1024, down_total/1024))

            if not os.access(os.path.dirname(output), os.F_OK):
                os.makedirs(os.path.dirname(output))
            self.outf = open(output, "w")
            def data(buf):
                self.outf.write(buf)

            # note that all redirects should already have been resolved by
            # this point; this is merely to check that the media that we are
            # trying to fetch actually exists
            ozutil.check_url(url)

            c = pycurl.Curl()
            c.setopt(c.URL, url)
            c.setopt(c.CONNECTTIMEOUT, 5)
            c.setopt(c.WRITEFUNCTION, data)
            c.setopt(c.NOPROGRESS, 0)
            c.setopt(c.PROGRESSFUNCTION, progress)
            # FIXME: if the perform fails, throw an error
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

        graphics_type = graphics[0].prop('type')
        port = graphics[0].prop('port')

        if graphics_type != 'vnc':
            self.log.error("Graphics type is not VNC, not taking screenshot")
            return

        if port is None:
            self.log.error("Port is not specified, not taking screenshot")
            return

        vncport = int(port) - 5900

        vnc = "localhost:" + str(vncport)
        ret = subprocess.call(['gvnccapture', vnc, filename], stdout=open('/dev/null', 'w'), stderr=subprocess.STDOUT)
        if ret != 0:
            self.log.error("Failed to take screenshot")

class CDGuest(Guest):
    def __init__(self, distro, update, arch, macaddr, nicmodel, clockoffset,
                 mousetype, diskbus):
        Guest.__init__(self, distro, update, arch, macaddr, nicmodel, clockoffset, mousetype, diskbus)
        self.orig_iso = "/var/lib/oz/isos/" + self.name + ".iso"
        self.output_iso = "/var/lib/libvirt/images/" + self.name + "-oz.iso"
        self.iso_contents = "/var/lib/oz/isocontent/" + self.name

    def get_original_iso(self, isourl):
        return self.get_original_media(isourl, self.orig_iso)

    def copy_iso(self):
        self.log.info("Copying ISO contents for modification")
        isomount = "/var/lib/oz/mnt/" + self.name
        if os.access(isomount, os.F_OK):
            os.rmdir(isomount)
        os.makedirs(isomount)

        if os.access(self.iso_contents, os.F_OK):
            shutil.rmtree(self.iso_contents)

        # mount and copy the ISO
        # this requires fuseiso to be installed
        subprocess_check_output(["fuseiso", self.orig_iso, isomount])

        try:
            shutil.copytree(isomount, self.iso_contents, symlinks=True)
        finally:
            # FIXME: if fusermount fails, what do we want to do?
            subprocess.call(["fusermount", "-u", isomount])
            os.rmdir(isomount)

    def install(self):
        self.log.info("Running install for %s" % (self.name))
        self.generate_define_xml("cdrom")
        self.libvirt_dom.create()

        self.wait_for_install_finish(1200)

        self.generate_define_xml("hd")

    def cleanup_iso(self):
        self.log.info("Cleaning up old ISO data")
        shutil.rmtree(self.iso_contents)

class FDGuest(Guest):
    def __init__(self, distro, update, arch, macaddr, nicmodel, clockoffset,
                 mousetype, diskbus):
        Guest.__init__(self, distro, update, arch, macaddr, nicmodel, clockoffset, mousetype, diskbus)
        self.orig_floppy = "/var/lib/oz/floppies/" + self.name + ".img"
        self.output_floppy = "/var/lib/libvirt/images/" + self.name + "-oz.img"
        self.floppy_contents = "/var/lib/oz/floppycontent/" + self.name

    def get_original_floppy(self, floppyurl):
        return self.get_original_media(floppyurl, self.orig_floppy)

    def copy_floppy(self):
        self.log.info("Copying floppy contents for modification")
        shutil.copyfile(self.orig_floppy, self.output_floppy)

    def install(self):
        self.log.info("Running install for %s" % (self.name))
        self.generate_define_xml("fd")
        self.libvirt_dom.create()

        self.wait_for_install_finish(1200)

        self.generate_define_xml("hd")
