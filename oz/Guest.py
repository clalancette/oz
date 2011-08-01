# Copyright (C) 2010,2011  Chris Lalancette <clalance@redhat.com>

# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation;
# version 2.1 of the License.

# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.

# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA

"""
Main class for guest installation
"""

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
import urlparse
import M2Crypto
import base64
import parted
import hashlib

import oz.ozutil
import oz.OzException

def subprocess_check_output(*popenargs, **kwargs):
    """
    Function to call a subprocess and gather the output.
    """
    if 'stdout' in kwargs:
        raise ValueError('stdout argument not allowed, it will be overridden.')
    if 'stderr' in kwargs:
        raise ValueError('stderr argument not allowed, it will be overridden.')

    oz.ozutil.executable_exists(popenargs[0][0])

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
        raise oz.OzException.OzException("'%s' failed(%d): %s" % (cmd, retcode,
                                                                  stderr))
    return (stdout, stderr, retcode)

class Guest(object):
    """
    Main class for guest installation.
    """
    def _get_conf(self, config, section, key, default):
        """
        Method to retrieve config parameters out of the config file.
        """
        if config is not None and config.has_section(section) \
                and config.has_option(section, key):
            return config.get(section, key)
        else:
            return default

    def _get_boolean_conf(self, config, section, key, default):
        """
        Method to retrieve boolean config parameters out of the config file.
        """
        value = self._get_conf(config, section, key, None)
        if value is None:
            return default

        retval = oz.ozutil.string_to_bool(value)
        if retval is None:
            raise oz.OzException.OzException("Configuration parameter '%s' must be True, Yes, False, or No" % (key))

        return retval

    def _discover_libvirt_type(self):
        """
        Internal method to discover the libvirt type (qemu, kvm, etc) that
        we should use, if not specified by the user.
        """
        if self.libvirt_type is None:
            try:
                stdout, stderr, retcode = subprocess_check_output(['virt-what'])
            except:
                self.log.warn("Could not determine hypervisor type (if any), trying to use KVM")
                stdout = ''

            if len(stdout) == 0:
                # if there was *nothing* printed, then this is probably a
                # bare-metal host.  Try to use KVM
                self.libvirt_type = 'kvm'
            else:
                # otherwise, this is probably some virtualization solution and
                # kvm will not work.  Try to use full emulation instead
                self.libvirt_type = 'qemu'

            # OK, we've discovered the type.  Check in with libvirt to see if
            # this is available on this machine
            libvirt_cap = self.libvirt_conn.getCapabilities()

            doc = libxml2.parseDoc(libvirt_cap)

            if len(doc.xpathEval("/capabilities/guest/arch/domain[@type='%s']" % (self.libvirt_type))) == 0:
                raise oz.OzException.OzException("This host does not support %s guests" % (self.libvirt_type))

        self.log.debug("Libvirt type is %s" % (self.libvirt_type))

    def _discover_libvirt_bridge(self):
        """
        Internal method to discover a libvirt bridge (if necessary).
        """
        if self.bridge_name is not None:
            # if the bridge name was specified in the config file, just detect
            # the IP address here
            self.host_bridge_ip = oz.ozutil.get_ip_from_interface(self.bridge_name)
        else:
            # otherwise, try to detect a private libvirt bridge
            for netname in self.libvirt_conn.listNetworks():
                network = self.libvirt_conn.networkLookupByName(netname)

                xml = network.XMLDesc(0)
                doc = libxml2.parseDoc(xml)

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
            raise oz.OzException.OzException("Could not find a viable libvirt NAT bridge, install cannot continue")

        self.log.debug("libvirt bridge name is %s, host_bridge_ip is %s" % (self.bridge_name, self.host_bridge_ip))

    def connect_to_libvirt(self):
        """
        Method to connect to libvirt and detect various things about the
        environment.
        """
        def _libvirt_error_handler(ctxt, err):
            """
            Error callback to suppress libvirt printing to stderr by default.
            """
            pass

        libvirt.registerErrorHandler(_libvirt_error_handler, 'context')
        self.libvirt_conn = libvirt.open(self.libvirt_uri)
        self._discover_libvirt_bridge()
        self._discover_libvirt_type()

    def __init__(self, tdl, nicmodel, clockoffset, mousetype, diskbus, config):
        self.tdl = tdl

        # for backwards compatibility
        self.name = self.tdl.name

        if self.tdl.arch != "i386" and self.tdl.arch != "x86_64":
            raise oz.OzException.OzException("Unsupported guest arch " + self.tdl.arch)
        self.log = logging.getLogger('%s.%s' % (__name__,
                                                self.__class__.__name__))
        self.uuid = uuid.uuid4()
        self.macaddr = oz.ozutil.generate_macaddress()

        # configuration from 'paths' section
        self.output_dir = self._get_conf(config, 'paths', 'output_dir',
                                         '/var/lib/libvirt/images')
        self.data_dir = self._get_conf(config, 'paths', 'data_dir',
                                       '/var/lib/oz')
        self.screenshot_dir = self._get_conf(config, 'paths', 'screenshot_dir',
                                             '.')

        # configuration from 'libvirt' section
        self.libvirt_uri = self._get_conf(config, 'libvirt', 'uri',
                                          'qemu:///system')
        self.libvirt_type = self._get_conf(config, 'libvirt', 'type', None)
        self.bridge_name = self._get_conf(config, 'libvirt', 'bridge_name',
                                          None)

        # configuration from 'cache' section
        self.cache_original_media = self._get_boolean_conf(config, 'cache',
                                                           'original_media',
                                                           True)
        self.cache_modified_media = self._get_boolean_conf(config, 'cache',
                                                           'modified_media',
                                                           False)
        self.cache_jeos = self._get_boolean_conf(config, 'cache', 'jeos', False)

        self.jeos_cache_dir = os.path.join(self.data_dir, "jeos")
        self.jeos_filename = os.path.join(self.jeos_cache_dir,
                                          self.tdl.distro + self.tdl.update + self.tdl.arch + ".dsk")

        self.diskimage = os.path.join(self.output_dir, self.tdl.name + ".dsk")
        self.icicle_tmp = os.path.join(self.data_dir, "icicletmp",
                                       self.tdl.name)
        self.listen_port = random.randrange(1024, 65535)

        self.connect_to_libvirt()

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
            raise oz.OzException.OzException("Unknown diskbus type " + diskbus)

        self.rootpw = self.tdl.rootpw
        if self.rootpw is None:
            self.rootpw = "ozrootpw"

        self.log.debug("Name: %s, UUID: %s" % (self.tdl.name, self.uuid))
        self.log.debug("MAC: %s, distro: %s" % (self.macaddr, self.tdl.distro))
        self.log.debug("update: %s, arch: %s, diskimage: %s" % (self.tdl.update, self.tdl.arch, self.diskimage))
        self.log.debug("nicmodel: %s, clockoffset: %s" % (self.nicmodel, self.clockoffset))
        self.log.debug("mousetype: %s, disk_bus: %s, disk_dev: %s" % (self.mousetype, self.disk_bus, self.disk_dev))
        self.log.debug("icicletmp: %s, listen_port: %d" % (self.icicle_tmp, self.listen_port))

    def cleanup_old_guest(self):
        """
        Method to completely clean up an old guest, including deleting the
        disk file.  Use with caution!
        """
        self.log.info("Cleaning up guest named %s" % (self.tdl.name))
        try:
            dom = self.libvirt_conn.lookupByName(self.tdl.name)
            try:
                dom.destroy()
            except libvirt.libvirtError:
                pass
            dom.undefine()
        except libvirt.libvirtError:
            pass

        if os.access(self.diskimage, os.F_OK):
            os.unlink(self.diskimage)

    def check_for_guest_conflict(self):
        """
        Method to check if any of our future actions will conflict with an
        already existing guest.  In particular, if a guest with the same
        name, UUID, or diskimage already exists, this throws an exception.
        """
        self.log.info("Checking for guest conflicts with %s" % (self.tdl.name))

        try:
            self.libvirt_conn.lookupByName(self.tdl.name)
            raise oz.OzException.OzException("Domain with name %s already exists" % (self.tdl.name))
        except libvirt.libvirtError:
            pass

        try:
            self.libvirt_conn.lookupByUUID(str(self.uuid))
            raise oz.OzException.OzException("Domain with UUID %s already exists" % (self.uuid))
        except libvirt.libvirtError:
            pass

        if os.access(self.diskimage, os.F_OK):
            raise oz.OzException.OzException("Diskimage %s already exists" % (self.diskimage))

    # the next 4 methods are intended to be overridden by the individual
    # OS backends; raise an error if they are called but not implemented

    def generate_install_media(self, force_download=False):
        """
        Base method for generating the install media for operating system
        installation.  This is expected to be overridden by all subclasses.
        """
        raise oz.OzException.OzException("Install media for %s%s is not implemented, install cannot continue" % (self.tdl.distro, self.tdl.update))

    def customize(self, libvirt_xml):
        """
        Base method for customizing the operating system.  This is expected
        to be overridden by subclasses that support customization.
        """
        raise oz.OzException.OzException("Customization for %s%s is not implemented" % (self.tdl.distro, self.tdl.update))

    def generate_icicle(self, libvirt_xml):
        """
        Base method for generating the ICICLE manifest from the operating
        system.  This is expect to be overridden by subclasses that support
        ICICLE generation.
        """
        raise oz.OzException.OzException("ICICLE generation for %s%s is not implemented" % (self.tdl.distro, self.tdl.update))

    # this method is intended to be an optimization if the user wants to do
    # both customize and generate_icicle
    def customize_and_generate_icicle(self, libvirt_xml):
        """
        Base method for doing operating system customization and ICICLE
        generation.  This is an optimization over doing the two steps
        separately for those classes that support customization and ICICLE
        generation.
        """
        raise oz.OzException.OzException("Customization and ICICLE generate for %s%s is not implemented" % (self.tdl.distro, self.tdl.update))

    class _InstallDev(object):
        """
        Class to hold information about an installation device.
        """
        def __init__(self, devicetype, path, bus):
            self.devicetype = devicetype
            self.path = path
            self.bus = bus

    def _generate_xml(self, bootdev, installdev):
        """
        Method to generate libvirt XML useful for installation.
        """
        self.log.info("Generate XML for guest %s with bootdev %s" % (self.tdl.name, bootdev))

        # create XML document
        doc = libxml2.newDoc("1.0")

        # create top-level domain element
        domain = doc.newChild(None, "domain", None)
        domain.setProp("type", self.libvirt_type)

        # create name element
        domain.newChild(None, "name", self.tdl.name)

        # create memory elements
        domain.newChild(None, "memory", "1048576")
        domain.newChild(None, "currentMemory", "1048576")

        # create uuid
        domain.newChild(None, "uuid", str(self.uuid))

        # create clock offset
        clock = domain.newChild(None, "clock", None)
        clock.setProp("offset", self.clockoffset)

        # create vcpu
        domain.newChild(None, "vcpu", "1")

        # create features
        features = domain.newChild(None, "features", None)
        features.newChild(None, "acpi", None)
        features.newChild(None, "apic", None)
        features.newChild(None, "pae", None)

        # create os
        osNode = domain.newChild(None, "os", None)
        osNode.newChild(None, "type", "hvm")
        boot = osNode.newChild(None, "boot", None)
        boot.setProp("dev", bootdev)

        # create poweroff, reboot, crash
        domain.newChild(None, "on_poweroff", "destroy")
        domain.newChild(None, "on_reboot", "destroy")
        domain.newChild(None, "on_crash", "destroy")

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
        # install disk (if any)
        if installdev:
            install = devices.newChild(None, "disk", None)
            install.setProp("type", "file")
            install.setProp("device", installdev.devicetype)
            source = install.newChild(None, "source", None)
            source.setProp("file", installdev.path)
            target = install.newChild(None, "target", None)
            target.setProp("dev", installdev.bus)

        xml = doc.serialize(None, 1)
        self.log.debug("Generated XML:\n%s" % (xml))

        return xml

    def _internal_generate_diskimage(self, size=10, force=False,
                                     create_partition=False):
        """
        Internal method to generate a diskimage.
        """
        if not force and os.access(self.jeos_filename, os.F_OK):
            # if we found a cached JEOS, we don't need to do anything here;
            # we'll copy the JEOS itself later on
            return

        self.log.info("Generating %dGB diskimage for %s" % (size,
                                                            self.tdl.name))

        f = open(self.diskimage, "w")
        f.truncate(size * 1024 * 1024 * 1024)
        f.close()

        if create_partition:
            dev = parted.Device(self.diskimage)
            disk = parted.freshDisk(dev, 'msdos')
            constraint = parted.Constraint(device=dev)
            geom = parted.Geometry(device=dev, start=1, end=2)
            partition = parted.Partition(disk=disk,
                                         type=parted.PARTITION_NORMAL,
                                         geometry=geom)
            disk.addPartition(partition=partition, constraint=constraint)
            disk.commit()

    def generate_diskimage(self, size=10, force=False):
        """
        Method to generate a diskimage.  By default, a blank diskimage of
        10GB will be created; the caller can override this with the size
        parameter, specified in GB.  If force is False (the default), then
        a diskimage will not be created if a cached JEOS is found.  If
        force is True, a diskimage will be created regardless of whether a
        cached JEOS exists.  See the oz-install man page for more information
        about JEOS caching.
        """
        return self._internal_generate_diskimage(size, force, False)

    def _wait_for_install_finish(self, libvirt_dom, count,
                                 inactivity_timeout=300):
        """
        Method to wait for an installation to finish.  This will wait around
        until either the VM has gone away (at which point it is assumed the
        install was successful), or until the timeout is reached (at which
        point it is assumed the install failed and raise an exception).
        """
        # first find the disk device we are installing to; this will be
        # monitored for activity during the installation
        domxml = libvirt_dom.XMLDesc(0)
        doc = libxml2.parseDoc(domxml)
        disktarget = doc.xpathEval("/domain/devices/disk[@device='disk']/target")
        if len(disktarget) < 1:
            raise oz.OzException.OzException("Could not find disk target")
        diskdev = disktarget[0].prop('dev')
        if diskdev is None:
            raise oz.OzException.OzException("Could not find disk target device")

        last_disk_activity = 0
        inactivity_countdown = inactivity_timeout
        origcount = count
        while count > 0:
            if count % 10 == 0:
                self.log.debug("Waiting for %s to finish installing, %d/%d" % (self.tdl.name, count, origcount))
            try:
                rd_req, rd_bytes, wr_req, wr_bytes, errs = libvirt_dom.blockStats(diskdev)
            except libvirt.libvirtError, e:
                if e.get_error_domain() == libvirt.VIR_FROM_QEMU and (e.get_error_code() in [libvirt.VIR_ERR_NO_DOMAIN, libvirt.VIR_ERR_SYSTEM_ERROR, libvirt.VIR_ERR_OPERATION_FAILED]):
                    break
                else:
                    self.log.debug("Libvirt Block Stats Failed:")
                    self.log.debug(" code is %d" % e.get_error_code())
                    self.log.debug(" domain is %d" % e.get_error_domain())
                    self.log.debug(" message is %s" % e.get_error_message())
                    self.log.debug(" level is %d" % e.get_error_level())
                    self.log.debug(" str1 is %s" % e.get_str1())
                    self.log.debug(" str2 is %s" % e.get_str2())
                    self.log.debug(" str3 is %s" % e.get_str3())
                    self.log.debug(" int1 is %d" % e.get_int1())
                    self.log.debug(" int2 is %d" % e.get_int2())
                    raise

            # if we saw no disk activity in the countdown window, we presume the
            # install has hung.  Fail here
            if inactivity_countdown == 0:
                screenshot_path = self._capture_screenshot(libvirt_dom.XMLDesc(0))
                exc_str = "No disk activity in %d seconds, failing.  " % (inactivity_timeout)
                if screenshot_path is not None:
                    exc_str += "Check screenshot at %s for more detail" % (screenshot_path)
                else:
                    exc_str += "Failed to take screenshot"
                raise oz.OzException.OzException(exc_str)

            if (rd_req + wr_req) == last_disk_activity:
                # if we saw no read or write requests since the last iteration,
                # decrement our activity timer
                inactivity_countdown -= 1
            else:
                # if we did see some activity, then we can reset the timer
                inactivity_countdown = inactivity_timeout

            last_disk_activity = rd_req + wr_req
            count -= 1
            time.sleep(1)

        if count == 0:
            # if we timed out, then let's make sure to take a screenshot.
            screenshot_path = self._capture_screenshot(libvirt_dom.XMLDesc(0))
            exc_str = "Timed out waiting for install to finish.  "
            if screenshot_path is not None:
                exc_str += "Check screenshot at %s for more detail" % (screenshot_path)
            else:
                exc_str += "Failed to take screenshot"
            raise oz.OzException.OzException(exc_str)

        self.log.info("Install of %s succeeded" % (self.tdl.name))

    def _wait_for_guest_shutdown(self, libvirt_dom, count=60):
        """
        Method to wait around for orderly shutdown of a running guest.  Returns
        True if the guest shutdown in the specified time, False otherwise.
        """
        origcount = count
        while count > 0:
            if count % 10 == 0:
                self.log.debug("Waiting for %s to shutdown, %d/%d" % (self.tdl.name, count, origcount))
            try:
                libvirt_dom.info()
            except libvirt.libvirtError, e:
                if e.get_error_domain() == libvirt.VIR_FROM_QEMU and (e.get_error_code() in [libvirt.VIR_ERR_NO_DOMAIN, libvirt.VIR_ERR_SYSTEM_ERROR, libvirt.VIR_ERR_OPERATION_FAILED]):
                    break
                else:
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
                    raise

            count -= 1
            time.sleep(1)

        return count != 0

    def _download_file(self, from_url, to, show_progress):
        """
        Internal method to download a file from from_url to file to.
        """
        self.last_mb = -1
        def _progress(down_total, down_current, up_total, up_current):
            """
            Method that is called back from the pycurl perform() method to
            update the progress information.
            """
            if down_total == 0:
                return
            current_mb = int(down_current) / 10485760
            if current_mb > self.last_mb or down_current == down_total:
                self.last_mb = current_mb
                self.log.debug("%dkB of %dkB" % (down_current/1024,
                                                 down_total/1024))

        self.outf = open(to, "w")
        def _data(buf):
            """
            Method that is called back from the pycurl perform() method to
            actually write data to disk.
            """
            self.outf.write(buf)

        c = pycurl.Curl()
        c.setopt(c.URL, from_url)
        c.setopt(c.CONNECTTIMEOUT, 5)
        c.setopt(c.WRITEFUNCTION, _data)
        if show_progress:
            c.setopt(c.NOPROGRESS, 0)
            c.setopt(c.PROGRESSFUNCTION, _progress)
        c.perform()
        c.close()
        self.outf.close()

    def _get_csums(self, original_url, output):
        """
        Internal method to fetch the checksum file and compute the checksum
        on the downloaded data.
        """
        outdir = os.path.dirname(output)
        self.mkdir_p(outdir)

        originalname = os.path.basename(urlparse.urlparse(original_url)[2])

        csumname = os.path.join(outdir,
                                self.tdl.distro + self.tdl.update + self.tdl.arch + "-CHECKSUM")

        if self.tdl.iso_md5_url:
            self.log.debug("Checksum requested, fetching MD5 file")
            self._download_file(self.tdl.iso_md5_url, csumname, False)
            upstream_sum = oz.ozutil.get_md5sum_from_file(csumname,
                                                          originalname)
            local_sum = hashlib.md5()
        elif self.tdl.iso_sha1_url:
            self.log.debug("Checksum requested, fetching SHA1 file")
            self._download_file(self.tdl.iso_sha1_url, csumname, False)
            upstream_sum = oz.ozutil.get_sha1sum_from_file(csumname,
                                                           originalname)
            local_sum = hashlib.sha1()
        else:
            self.log.debug("Checksum requested, fetching SHA256 file")
            self._download_file(self.tdl.iso_sha256_url, csumname, False)
            upstream_sum = oz.ozutil.get_sha256sum_from_file(csumname,
                                                             originalname)
            local_sum = hashlib.sha256()

        os.unlink(csumname)

        if not upstream_sum:
            raise oz.OzException.OzException("Could not find checksum for original file " + originalname)

        self.log.debug("Calculating checksum of downloaded file")
        f = open(output, 'r')
        for line in f.xreadlines():
            local_sum.update(line)
        f.close()

        return local_sum.hexdigest(), upstream_sum

    def _get_original_media(self, url, output, force_download):
        """
        Method to fetch the original media from url.  If the media is already
        cached locally, the cached copy will be used instead.
        """
        self.log.info("Fetching the original media")

        response = urllib2.urlopen(url)
        url = response.geturl()
        info = response.info()
        response.close()

        if not info.has_key("Content-Length"):
            raise oz.OzException.OzException("Could not reach destination to fetch boot media")
        content_length = int(info["Content-Length"])
        if content_length == 0:
            raise oz.OzException.OzException("Install media of 0 size detected, something is wrong")

        if not force_download and os.access(output, os.F_OK):
            if content_length == os.stat(output)[stat.ST_SIZE]:
                if self.tdl.iso_md5_url or self.tdl.iso_sha1_url or self.tdl.iso_sha256_url:
                    local_sum, upstream_sum = self._get_csums(url, output)
                    if local_sum == upstream_sum:
                        self.log.info("Original install media available and matches checksum, using cached version")
                        return
                    else:
                        self.log.info("Original available, but checksum mis-match; re-downloading")
                else:
                    # no checksum given, just assume it is good enough; this
                    # preserves backwards compatible behavior
                    self.log.info("Original install media available, using cached version")
                    return

        # before fetching everything, make sure that we have enough
        # space on the filesystem to store the data we are about to download
        outdir = os.path.dirname(output)
        self.mkdir_p(outdir)
        devdata = os.statvfs(outdir)
        if (devdata.f_bsize*devdata.f_bavail) < content_length:
            raise oz.OzException.OzException("Not enough room on %s for install media" % (outdir))
        self.log.info("Fetching the original install media from %s" % (url))
        self._download_file(url, output, True)

        filesize = os.stat(output)[stat.ST_SIZE]

        if filesize != content_length:
            # if the length we downloaded is not the same as what we originally
            # saw from the headers, something went wrong
            raise oz.OzException.OzException("Expected to download %d bytes, downloaded %d" % (content_length, filesize))

        if self.tdl.iso_md5_url or self.tdl.iso_sha1_url or self.tdl.iso_sha256_url:
            local_sum, upstream_sum = self._get_csums(url, output)
            if local_sum != upstream_sum:
                raise oz.OzException.OzException("Checksum for downloaded file does not match!")
            else:
                self.log.debug("Checksum matches")

    def _capture_screenshot(self, xml):
        """
        Method to capture a screenshot of the VM.
        """
        screenshot = os.path.realpath(os.path.join(self.screenshot_dir,
                                                   self.tdl.name + "-" + str(time.time()) + ".png"))

        doc = libxml2.parseDoc(xml)
        graphics = doc.xpathEval('/domain/devices/graphics')
        if len(graphics) != 1:
            self.log.error("Could not find the VNC port, not take screenshot")
            return None

        if graphics[0].prop('type') != 'vnc':
            self.log.error("Graphics type is not VNC, not taking screenshot")
            return None

        port = graphics[0].prop('port')

        if port is None:
            self.log.error("Port is not specified, not taking screenshot")
            return None

        vnc = "localhost:%s" % (int(port) - 5900)

        try:
            subprocess_check_output(['gvnccapture', vnc, screenshot])
            return screenshot
        except:
            self.log.error("Failed to take screenshot")
            return None

    def _guestfs_handle_setup(self, libvirt_xml):
        """
        Method to setup a guestfs handle to the guest disks.
        """
        input_doc = libxml2.parseDoc(libvirt_xml)
        namenode = input_doc.xpathEval('/domain/name')
        if len(namenode) != 1:
            raise oz.OzException.OzException("invalid libvirt XML with no name")
        input_name = namenode[0].getContent()
        disks = input_doc.xpathEval('/domain/devices/disk')
        if len(disks) != 1:
            raise oz.OzException.OzException("oz cannot handle a libvirt domain with more than 1 disk")
        source = disks[0].xpathEval('source')
        if len(source) != 1:
            raise oz.OzException.OzException("invalid <disk> entry without a source")
        input_disk = source[0].prop('file')
        driver = disks[0].xpathEval('driver')
        if len(driver) == 0:
            input_disk_type = 'raw'
        elif len(driver) == 1:
            input_disk_type = driver[0].prop('type')
        else:
            raise oz.OzException.OzException("invalid <disk> entry without a driver")

        for domid in self.libvirt_conn.listDomainsID():
            self.log.debug("DomID: %d" % (domid))
            dom = self.libvirt_conn.lookupByID(domid)
            xml = dom.XMLDesc(0)
            doc = libxml2.parseDoc(xml)
            namenode = doc.xpathEval('/domain/name')
            if len(namenode) != 1:
                # hm, odd, a domain without a name?
                raise oz.OzException.OzException("Saw a domain without a name, something weird is going on")
            if input_name == namenode[0].getContent():
                raise oz.OzException.OzException("Cannot setup ICICLE generation on a running guest")
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
                        raise oz.OzException.OzException("Cannot setup ICICLE generation on a running disk")


        self.log.info("Setting up guestfs handle for %s" % (self.tdl.name))
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
            raise oz.OzException.OzException("No operating systems found on the disk")

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
            def _compare(a, b):
                """
                Method to sort disks by length.
                """
                if len(a[0]) > len(b[0]):
                    return 1
                elif len(a[0]) == len(b[0]):
                    return 0
                else:
                    return -1
            mps.sort(_compare)
            for mp_dev in mps:
                g.mount_options('', mp_dev[1], mp_dev[0])

        return g

    def _guestfs_handle_cleanup(self, g_handle):
        """
        Method to cleanup a handle previously setup by __guestfs_handle_setup.
        """
        self.log.info("Cleaning up guestfs handle for %s" % (self.tdl.name))
        self.log.debug("Syncing")
        g_handle.sync()

        self.log.debug("Unmounting all")
        g_handle.umount_all()

        self.log.debug("Killing guestfs subprocess")
        g_handle.kill_subprocess()

    def _wait_for_guest_boot(self, libvirt_dom):
        """
        Method to wait around for a guest to boot.  Orderly guests will boot
        up and announce their presence via a TCP message; if that happens within
        the timeout, this method returns the IP address of the guest.  If that
        doesn't happen an exception is raised.
        """
        self.log.info("Waiting for guest %s to boot" % (self.tdl.name))

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
                    if count % 10 == 0:
                        self.log.debug("Waiting for guest %s to boot, %d/300" % (self.tdl.name, count))
                    rlist, wlist, xlist = select.select([listen], [], [], 1)
                    if len(rlist) > 0:
                        # OK, something connected to the socket.  Read some
                        # data from the socket and make sure it matches the
                        # 'secret' (i.e. the guest UUID).  If it does, the
                        # guest checked in.  If not, this is a connection from
                        # something else, and we should ignore it.
                        new_sock, addr = listen.accept()
                        new_sock.settimeout(10)
                        data = new_sock.recv(len(str(self.uuid)))
                        new_sock.close()

                        if data == str(self.uuid):
                            break

                    # OK, the guest hasn't checked in yet.  Do an "info" on
                    # the domain just to make sure it is still alive.  If it
                    # isn't, this will throw an exception (which is what
                    # we want)
                    libvirt_dom.info()

                    count -= 1
            finally:
                try:
                    subprocess_check_output(["iptables", "-D", "INPUT", "1"])
                except:
                    self.log.warn("Failed to delete iptables rule")
        finally:
            listen.close()

        if addr is None:
            raise oz.OzException.OzException("Timed out waiting for domain to boot")

        self.log.debug("IP address of guest is %s" % (addr[0]))

        return addr[0]

    def _output_icicle_xml(self, lines, description):
        """
        Generate ICICLE XML based on the data supplied.
        """
        doc = libxml2.newDoc("1.0")
        icicle = doc.newChild(None, "icicle", None)
        if description is not None:
            description = icicle.newChild(None, "description", description)
        packages = icicle.newChild(None, "packages", None)

        lines.sort()
        for line in lines:
            if line == "":
                continue
            package = packages.newChild(None, "package", None)
            package.setProp("name", line)

        return doc.serialize(None, 1)

    def mkdir_p(self, path):
        """
        Create a directory and all of its parents.
        """
        if not os.access(path, os.F_OK):
            os.makedirs(path)

    def _check_url(self, tdl, iso=True, url=True):
        """
        Method to check that a TDL URL meets the requirements for a particular
        operating system.
        """
        if iso and tdl.installtype == 'iso':
            url = tdl.iso
        elif url and tdl.installtype == 'url':
            url = tdl.url

            # when doing URL installs, we can't allow localhost URLs (the URL
            # will be embedded into the installer, so the install is guaranteed
            # to fail with localhost URLs).  Disallow them here
            p = urlparse.urlparse(url)
            if p[1] in ["localhost", "localhost.localdomain", "127.0.0.1"]:
                raise oz.OzException.OzException("Can not use localhost for an URL based install")
        else:
            if iso and url:
                raise oz.OzException.OzException("%s installs must be done via url or iso" % (tdl.distro))
            elif iso:
                raise oz.OzException.OzException("%s installs must be done via iso" % (tdl.distro))
            elif url:
                raise oz.OzException.OzException("%s installs must be done via url" % (tdl.distro))
            else:
                raise oz.OzException.OzException("Unknown error occured while determining install URL")

        return url

    def _generate_openssh_key(self, privname):
        """
        Method to generate an OpenSSH compatible public/private keypair.
        """
        self.log.info("Generating new openssh key")
        pubname = privname + ".pub"
        if os.access(privname, os.F_OK) and not os.access(pubname, os.F_OK):
            # hm, private key exists but not public?  We have to regenerate
            os.remove(privname)

        if not os.access(privname, os.F_OK) and os.access(pubname, os.F_OK):
            # hm, public key exists but not private?  We have to regenerate
            os.remove(pubname)

        # when we get here, either both the private and public key exist, or
        # neither exist.  If they don't exist, generate them
        if not os.access(privname, os.F_OK) and not os.access(pubname, os.F_OK):
            def _null_callback(p, n, out):
                """
                Method to silence the default M2Crypto.RSA.gen_key output.
                """
                pass

            pubname = privname + '.pub'

            key = M2Crypto.RSA.gen_key(2048, 65537, _null_callback)

            # this is the binary public key, in ssh "BN" (BigNumber) MPI format.
            # The ssh BN MPI format consists of 4 bytes that describe the length
            # of the following data, followed by the data itself in big-endian
            # format.  The start of the string is 0x0007, which represent the 7
            # bytes following that make up 'ssh-rsa'.  The key exponent and
            # modulus as fetched out of M2Crypto are already in MPI format, so
            # we can just use them as-is.  We then have to base64 encode the
            # result, add a little header information, and then we have a
            # full public key.
            pubkey = '\x00\x00\x00\x07' + 'ssh-rsa' + key.e + key.n

            username = os.getlogin()
            hostname = os.uname()[1]
            keystring = 'ssh-rsa %s %s@%s\n' % (base64.b64encode(pubkey),
                                                username, hostname)

            key.save_key(privname, cipher=None)
            os.chmod(privname, 0600)
            open(pubname, 'w').write(keystring)
            os.chmod(pubname, 0644)

    def _copy_modify_file(self, inname, outname, subfunc):
        """
        Method to copy a file from inname to outname, passing each line
        through subfunc first.  subfunc is expected to be a method that
        takes a single argument in (the next line), and returns a string
        to be written to the output file after modification (if any).
        """
        infile = open(inname, 'r')
        outfile = open(outname, 'w')

        for line in infile.xreadlines():
            outfile.write(subfunc(line))

        infile.close()
        outfile.close()

class CDGuest(Guest):
    """
    Class for guest installation via ISO.
    """
    class _PrimaryVolumeDescriptor(object):
        """
        Class to hold information about a CD's Primary Volume Descriptor.
        """
        def __init__(self, version, sysid, volid, space_size, set_size, seqnum):
            self.version = version
            self.system_identifier = sysid
            self.volume_identifier = volid
            self.space_size = space_size
            self.set_size = set_size
            self.seqnum = seqnum

    def __init__(self, tdl, nicmodel, clockoffset, mousetype, diskbus, config):
        Guest.__init__(self, tdl, nicmodel, clockoffset, mousetype, diskbus,
                       config)

        self.orig_iso = os.path.join(self.data_dir, "isos",
                                     self.tdl.distro + self.tdl.update + self.tdl.arch + "-" + self.tdl.installtype + ".iso")
        self.modified_iso_cache = os.path.join(self.data_dir, "isos",
                                               self.tdl.distro + self.tdl.update + self.tdl.arch + "-" + self.tdl.installtype + "-oz.iso")
        self.output_iso = os.path.join(self.output_dir,
                                       self.tdl.name + "-" + self.tdl.installtype + "-oz.iso")
        self.iso_contents = os.path.join(self.data_dir, "isocontent",
                                         self.tdl.name + "-" + self.tdl.installtype)

        self.log.debug("Original ISO path: %s" % self.orig_iso)
        self.log.debug("Modified ISO cache: %s" % self.modified_iso_cache)
        self.log.debug("Output ISO path: %s" % self.output_iso)
        self.log.debug("ISO content path: %s" % self.iso_contents)

    def _get_original_iso(self, isourl, force_download):
        """
        Method to fetch the original ISO for an operating system.
        """
        self._get_original_media(isourl, self.orig_iso, force_download)

    def _copy_iso(self):
        """
        Method to copy the data out of an ISO onto the local filesystem.
        """
        self.log.info("Copying ISO contents for modification")
        if os.access(self.iso_contents, os.F_OK):
            shutil.rmtree(self.iso_contents)
        os.makedirs(self.iso_contents)

        self.log.info("Setting up guestfs handle for %s" % (self.tdl.name))
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
                raise oz.OzException.OzException("Not enough room on %s to extract install media" % (self.iso_contents))

            self.log.debug("Extracting ISO contents")
            current = os.getcwd()
            os.chdir(self.iso_contents)
            try:
                rd, wr = os.pipe()

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

    def _get_primary_volume_descriptor(self, cdfile):
        """
        Method to extract the primary volume descriptor from a CD.
        """
        cdfile = open(cdfile, "r")

        # check out the primary volume descriptor to make sure it is sane
        cdfile.seek(16*2048)
        fmt = "=B5sBB32s32sQLL32sHHHH"
        (desc_type, identifier, version, unused1, system_identifier, volume_identifier, unused2, space_size_le, space_size_be, unused3, set_size_le, set_size_be, seqnum_le, seqnum_be) = struct.unpack(fmt, cdfile.read(struct.calcsize(fmt)))
        cdfile.close()

        if desc_type != 0x1:
            raise oz.OzException.OzException("Invalid primary volume descriptor")
        if identifier != "CD001":
            raise oz.OzException.OzException("invalid CD isoIdentification")
        if unused1 != 0x0:
            raise oz.OzException.OzException("data in unused field")
        if unused2 != 0x0:
            raise oz.OzException.OzException("data in 2nd unused field")

        return self._PrimaryVolumeDescriptor(version, system_identifier,
                                             volume_identifier, space_size_le,
                                             set_size_le, seqnum_le)

    def _geteltorito(self, cdfile, outfile):
        """
        Method to extract the El-Torito boot sector off of a CD and write it
        to a file.
        """
        self._get_primary_volume_descriptor(cdfile)

        cdfile = open(cdfile, "r")

        # the 17th sector contains the boot specification and the offset of the
        # boot sector
        cdfile.seek(17*2048)

        # NOTE: With "native" alignment (the default for struct), there is
        # some padding that happens that causes the unpacking to fail.
        # Instead we force "standard" alignment, which has no padding
        fmt = "=B5sB23s41sI"
        (boot, isoIdent, version, toritoSpec, unused, bootP) = struct.unpack(fmt,
                                                                             cdfile.read(struct.calcsize(fmt)))
        if boot != 0x0:
            raise oz.OzException.OzException("invalid CD boot sector")
        if version != 0x1:
            raise oz.OzException.OzException("invalid CD version")
        if isoIdent != "CD001":
            raise oz.OzException.OzException("invalid CD isoIdentification")
        if toritoSpec != "EL TORITO SPECIFICATION":
            raise oz.OzException.OzException("invalid CD torito specification")

        # OK, this looks like a bootable CD.  Seek to the boot sector, and
        # look for the header, 0x55, and 0xaa in the first 32 bytes
        cdfile.seek(bootP*2048)
        fmt = "=BBH24sHBB"
        bootdata = cdfile.read(struct.calcsize(fmt))
        (header, platform, unused, manu, unused2, five, aa) = struct.unpack(fmt,
                                                                            bootdata)
        if header != 0x1:
            raise oz.OzException.OzException("invalid CD boot sector header")
        if platform != 0x0 and platform != 0x1 and platform != 0x2:
            raise oz.OzException.OzException("invalid CD boot sector platform")
        if unused != 0x0:
            raise oz.OzException.OzException("invalid CD unused boot sector field")
        if five != 0x55 or aa != 0xaa:
            raise oz.OzException.OzException("invalid CD boot sector footer")

        def _checksum(data):
            """
            Method to compute the 1's complement checksum on the ISO.
            """
            s = 0
            for i in range(0, len(data), 2):
                w = ord(data[i]) + (ord(data[i+1]) << 8)
                s = numpy.uint16(numpy.uint16(s) + numpy.uint16(w))
            return s

        csum = _checksum(bootdata)
        if csum != 0:
            raise oz.OzException.OzException("invalid CD checksum: expected 0, saw %d" % (csum))

        # OK, everything so far has checked out.  Read the default/initial
        # boot entry
        cdfile.seek(bootP*2048+32)
        fmt = "=BBHBBHIB"
        (boot, media, loadsegment, systemtype, unused, scount, imgstart, unused2) = struct.unpack(fmt, cdfile.read(struct.calcsize(fmt)))

        if boot != 0x88:
            raise oz.OzException.OzException("invalid CD initial boot indicator")
        if unused != 0x0 or unused2 != 0x0:
            raise oz.OzException.OzException("invalid CD initial boot unused field")

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
            raise oz.OzException.OzException("invalid CD media type")

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

    def _do_install(self, timeout=None, force=False, reboots=0):
        """
        Internal method to actually run the installation.
        """
        if not force and os.access(self.jeos_filename, os.F_OK):
            self.log.info("Found cached JEOS, using it")
            oz.ozutil.copyfile_sparse(self.jeos_filename, self.diskimage)
        else:
            self.log.info("Running install for %s" % (self.tdl.name))

            cddev = self._InstallDev("cdrom", self.output_iso, "hdc")

            if timeout is None:
                timeout = 1200

            dom = self.libvirt_conn.createXML(self._generate_xml("cdrom",
                                                                 cddev), 0)
            self._wait_for_install_finish(dom, timeout)

            for i in range(0, reboots):
                dom = self.libvirt_conn.createXML(self._generate_xml("hd",
                                                                     cddev), 0)
                self._wait_for_install_finish(dom, timeout)

            if self.cache_jeos:
                self.log.info("Caching JEOS")
                self.mkdir_p(self.jeos_cache_dir)
                oz.ozutil.copyfile_sparse(self.diskimage, self.jeos_filename)

        return self._generate_xml("hd", None)

    def install(self, timeout=None, force=False):
        """
        Method to run the operating system installation.
        """
        return self._do_install(timeout, force, 0)

    def _check_pvd(self):
        """
        Base method to check the Primary Volume Descriptor on the ISO.  In the
        common case, do nothing; subclasses that need to check the media will
        override this.
        """
        pass

    def _check_iso_tree(self):
        """
        Base method to check the exploded ISO tree.  In the common case, do
        nothing; subclasses that need to check the tree will override this.
        """
        pass

    def _modify_iso(self):
        """
        Base method to modify the ISO.  Subclasses are expected to override this
        """
        raise oz.OzException.OzException("Internal error, subclass didn't override modify_iso")

    def _generate_new_iso(self):
        """
        Base method to generate the new ISO.  Subclasses are expected to
        override this
        """
        raise oz.OzException.OzException("Internal error, subclass didn't override generate_new_iso")

    def _iso_generate_install_media(self, url, force_download):
        """
        Method to generate the modified media necessary for unattended installs.
        """
        self.log.info("Generating install media")

        if not force_download:
            if os.access(self.jeos_filename, os.F_OK):
                # if we found a cached JEOS, we don't need to do anything here;
                # we'll copy the JEOS itself later on
                return
            elif os.access(self.modified_iso_cache, os.F_OK):
                self.log.info("Using cached modified media")
                shutil.copyfile(self.modified_iso_cache, self.output_iso)
                return

        self._get_original_iso(url, force_download)
        self._check_pvd()
        self._copy_iso()
        self._check_iso_tree()
        try:
            self._modify_iso()
            self._generate_new_iso()
            if self.cache_modified_media:
                self.log.info("Caching modified media for future use")
                shutil.copyfile(self.output_iso, self.modified_iso_cache)
        finally:
            self._cleanup_iso()

    def _cleanup_iso(self):
        """
        Method to cleanup the local ISO contents.
        """
        self.log.info("Cleaning up old ISO data")
        shutil.rmtree(self.iso_contents)

    def cleanup_install(self):
        """
        Method to cleanup any transient install data.
        """
        self.log.info("Cleaning up after install")
        # the modified ISO may not exist if we did a JEOS copy instead of a
        # full install
        if os.access(self.output_iso, os.F_OK):
            self.log.debug("Removing modified ISO")
            os.unlink(self.output_iso)
        # the original ISO may not exist if we did a JEOS copy instead of a
        # full install
        if not self.cache_original_media and os.access(self.orig_iso, os.F_OK):
            self.log.debug("Removing original ISO")
            os.unlink(self.orig_iso)

class FDGuest(Guest):
    """
    Class for guest installation via floppy disk.
    """
    def __init__(self, tdl, nicmodel, clockoffset, mousetype, diskbus, config):
        Guest.__init__(self, tdl, nicmodel, clockoffset, mousetype, diskbus,
                       config)
        self.orig_floppy = os.path.join(self.data_dir, "floppies",
                                        self.tdl.distro + self.tdl.update + self.tdl.arch + ".img")
        self.modified_floppy_cache = os.path.join(self.data_dir, "floppies",
                                                  self.tdl.distro + self.tdl.update + self.tdl.arch + "-oz.img")
        self.output_floppy = os.path.join(self.output_dir,
                                          self.tdl.name + "-oz.img")
        self.floppy_contents = os.path.join(self.data_dir, "floppycontent",
                                            self.tdl.name)

        self.log.debug("Original floppy path: %s" % self.orig_floppy)
        self.log.debug("Modified floppy cache: %s" % self.modified_floppy_cache)
        self.log.debug("Output floppy path: %s" % self.output_floppy)
        self.log.debug("Floppy content path: %s" % self.floppy_contents)

    def _get_original_floppy(self, floppyurl, force_download):
        """
        Method to download the original floppy if necessary.
        """
        self._get_original_media(floppyurl, self.orig_floppy, force_download)

    def _copy_floppy(self):
        """
        Method to copy the floppy contents for modification.
        """
        self.log.info("Copying floppy contents for modification")
        shutil.copyfile(self.orig_floppy, self.output_floppy)

    def install(self, timeout=None, force=False):
        """
        Method to run the operating system installation.
        """
        if not force and os.access(self.jeos_filename, os.F_OK):
            self.log.info("Found cached JEOS, using it")
            oz.ozutil.copyfile_sparse(self.jeos_filename, self.diskimage)
        else:
            self.log.info("Running install for %s" % (self.tdl.name))

            fddev = self._InstallDev("floppy", self.output_floppy, "fda")

            if timeout is None:
                timeout = 1200

            dom = self.libvirt_conn.createXML(self._generate_xml("fd", fddev),
                                              0)
            self._wait_for_install_finish(dom, timeout)

            if self.cache_jeos:
                self.log.info("Caching JEOS")
                self.mkdir_p(self.jeos_cache_dir)
                oz.ozutil.copyfile_sparse(self.diskimage, self.jeos_filename)

        return self._generate_xml("hd", None)

    def _cleanup_floppy(self):
        """
        Method to cleanup the temporary floppy data.
        """
        self.log.info("Cleaning up floppy data")
        shutil.rmtree(self.floppy_contents)

    def cleanup_install(self):
        """
        Method to cleanup the installation floppies.
        """
        self.log.info("Cleaning up after install")
        os.unlink(self.output_floppy)
        self.log.debug("Removed modified floppy")
        if not self.cache_original_media:
            os.unlink(self.orig_floppy)
