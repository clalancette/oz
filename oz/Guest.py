# Copyright (C) 2010,2011  Chris Lalancette <clalance@redhat.com>
# Copyright (C) 2012-2018  Chris Lalancette <clalancette@gmail.com>

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

import base64
import errno
import hashlib
import logging
import os
import re
import shutil
import socket
import stat
import struct
import subprocess
import tempfile
import time
try:
    import urllib.parse as urlparse
except ImportError:
    import urlparse
import uuid

import M2Crypto

import guestfs

import libvirt

import lxml.etree

import oz.GuestFSManager
import oz.OzException
import oz.ozutil


class Guest(object):
    """
    Main class for guest installation.
    """
    def _discover_libvirt_type(self):
        """
        Internal method to discover the libvirt type (qemu, kvm, etc) that
        we should use, if not specified by the user.
        """
        if self.libvirt_type is None:
            doc = lxml.etree.fromstring(self.libvirt_conn.getCapabilities())

            # Libvirt calls the old intel 32-bit architecture i686, while we
            # refer to it as i386.  Do the mapping here, since we need to look
            # up the libvirt name.
            libvirtarch = self.tdl.arch
            if libvirtarch == 'i386':
                libvirtarch = 'i686'

            if len(doc.xpath("/capabilities/guest/arch[@name='%s']/domain[@type='kvm']" % (libvirtarch))) > 0:
                self.libvirt_type = 'kvm'
            elif len(doc.xpath("/capabilities/guest/arch[@name='%s']/domain[@type='qemu']" % (libvirtarch))) > 0:
                self.libvirt_type = 'qemu'
            else:
                raise oz.OzException.OzException("This host does not support virtualization type kvm or qemu for TDL arch (%s)" % (libvirtarch))

        self.log.debug("Libvirt type is %s", self.libvirt_type)

    def _discover_libvirt_bridge(self):
        """
        Internal method to discover a libvirt bridge (if necessary).
        """
        if self.bridge_name is None:
            # otherwise, try to detect a private libvirt bridge
            for netname in self.libvirt_conn.listNetworks():
                network = self.libvirt_conn.networkLookupByName(netname)

                xml = network.XMLDesc(0)
                doc = lxml.etree.fromstring(xml)

                forward = doc.xpath('/network/forward')
                if len(forward) != 1:
                    self.log.warning("Libvirt network without a forward element, skipping")
                    continue

                if forward[0].get('mode') == 'nat':
                    ips = doc.xpath('/network/ip')
                    if not ips:
                        self.log.warning("Libvirt network without an IP, skipping")
                        continue
                    for ip in ips:
                        family = ip.get("family")
                        if family is None or family == "ipv4":
                            self.bridge_name = network.bridgeName()
                            break

        if self.bridge_name is None:
            raise oz.OzException.OzException("Could not find a libvirt bridge.  Please run 'virsh net-start default' to start the default libvirt network, or see http://github.com/clalancette/oz/wiki/Oz-Network-Configuration for more information")

        self.log.debug("libvirt bridge name is %s", self.bridge_name)

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

    def __init__(self, tdl, config, auto, output_disk, nicmodel, clockoffset,
                 mousetype, diskbus, iso_allowed, url_allowed, macaddress):
        self.tdl = tdl

        # for backwards compatibility
        self.name = self.tdl.name

        if self.tdl.arch not in ["i386", "x86_64", "ppc64", "ppc64le", "aarch64", "armv7l", "s390x"]:
            raise oz.OzException.OzException("Unsupported guest arch " + self.tdl.arch)

        if os.uname()[4] in ["i386", "i586", "i686"] and self.tdl.arch == "x86_64":
            raise oz.OzException.OzException("Host machine is i386, but trying to install x86_64 guest; this cannot work")

        self.log = logging.getLogger('%s.%s' % (__name__,
                                                self.__class__.__name__))
        self.uuid = uuid.uuid4()
        self.macaddr = macaddress
        if macaddress is None:
            self.macaddr = oz.ozutil.generate_macaddress()

        # configuration from 'paths' section
        self.output_dir = oz.ozutil.config_get_path(config, 'paths',
                                                    'output_dir',
                                                    oz.ozutil.default_output_dir())

        oz.ozutil.mkdir_p(self.output_dir)

        self.data_dir = oz.ozutil.config_get_path(config, 'paths',
                                                  'data_dir',
                                                  oz.ozutil.default_data_dir())

        self.screenshot_dir = oz.ozutil.config_get_path(config, 'paths',
                                                        'screenshot_dir',
                                                        oz.ozutil.default_screenshot_dir())

        self.sshprivkey = oz.ozutil.config_get_path(config, 'paths',
                                                    'sshprivkey',
                                                    oz.ozutil.default_sshprivkey())

        # configuration from 'libvirt' section
        self.libvirt_uri = oz.ozutil.config_get_key(config, 'libvirt', 'uri',
                                                    'qemu:///system')
        self.libvirt_type = oz.ozutil.config_get_key(config, 'libvirt', 'type',
                                                     None)
        self.bridge_name = oz.ozutil.config_get_key(config, 'libvirt',
                                                    'bridge_name', None)
        self.install_cpus = oz.ozutil.config_get_key(config, 'libvirt', 'cpus',
                                                     1)
        # the memory in the configuration file is specified in megabytes, but
        # libvirt expects kilobytes, so multiply by 1024
        if self.tdl.arch in ["ppc64", "ppc64le"]:
            # ppc64 needs at least 2Gb RAM
            self.install_memory = int(oz.ozutil.config_get_key(config, 'libvirt',
                                                               'memory', 2048)) * 1024
        else:
            self.install_memory = int(oz.ozutil.config_get_key(config, 'libvirt',
                                                               'memory', 1024)) * 1024
        self.image_type = oz.ozutil.config_get_key(config, 'libvirt',
                                                   'image_type', 'raw')

        # configuration from 'cache' section
        self.cache_original_media = oz.ozutil.config_get_boolean_key(config,
                                                                     'cache',
                                                                     'original_media',
                                                                     True)
        self.cache_modified_media = oz.ozutil.config_get_boolean_key(config,
                                                                     'cache',
                                                                     'modified_media',
                                                                     False)
        self.cache_jeos = oz.ozutil.config_get_boolean_key(config, 'cache',
                                                           'jeos', False)

        self.jeos_cache_dir = os.path.join(self.data_dir, "jeos")

        # configuration of "safe" ICICLE generation option
        self.safe_icicle_gen = oz.ozutil.config_get_boolean_key(config,
                                                                'icicle',
                                                                'safe_generation',
                                                                False)

        # configuration of 'timeouts' section
        self.default_install_timeout = int(oz.ozutil.config_get_key(config, 'timeouts',
                                                                    'install', 1200))
        self.inactivity_timeout = int(oz.ozutil.config_get_key(config, 'timeouts',
                                                               'inactivity', 300))
        self.boot_timeout = int(oz.ozutil.config_get_key(config, 'timeouts',
                                                         'boot', 300))
        self.shutdown_timeout = int(oz.ozutil.config_get_key(config, 'timeouts',
                                                             'shutdown', 90))

        # only pull a cached JEOS if it was built with the correct image type
        jeos_extension = self.image_type
        if self.image_type == 'raw':
            # backwards compatible
            jeos_extension = 'dsk'

        self.jeos_filename = os.path.join(self.jeos_cache_dir,
                                          self.tdl.distro + self.tdl.update + self.tdl.arch + '.' + jeos_extension)

        self.diskimage = output_disk
        if self.diskimage is None:
            ext = "." + self.image_type
            # compatibility with older versions of Oz
            if self.image_type == 'raw':
                ext = '.dsk'
            self.diskimage = os.path.join(self.output_dir, self.tdl.name + ext)

        if not os.path.isabs(self.diskimage):
            raise oz.OzException.OzException("Output disk image must be an absolute path")

        self.icicle_tmp = os.path.join(self.data_dir, "icicletmp",
                                       self.tdl.name)

        self.listen_port = oz.ozutil.get_free_port()

        self.console_listen_port = oz.ozutil.get_free_port()

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

        try:
            # PPC64 directory structure differs from x86; disabling ISO boots
            if self.tdl.arch not in ["ppc64", "ppc64le"]:
                self.url = self._check_url(iso=iso_allowed, url=url_allowed)
            else:
                self.url = self._check_url(iso=False, url=url_allowed)
        except:
            self.log.debug("Install URL validation failed:", exc_info=True)
            raise

        oz.ozutil.mkdir_p(self.icicle_tmp)

        self.disksize = 10
        if self.tdl.disksize is not None:
            self.disksize = int(self.tdl.disksize)

        self.auto = auto
        if self.auto is None:
            self.auto = self.get_auto_path()

        self.log.debug("Name: %s, UUID: %s", self.tdl.name, self.uuid)
        self.log.debug("MAC: %s, distro: %s", self.macaddr, self.tdl.distro)
        self.log.debug("update: %s, arch: %s, diskimage: %s", self.tdl.update, self.tdl.arch, self.diskimage)
        self.log.debug("nicmodel: %s, clockoffset: %s", self.nicmodel, self.clockoffset)
        self.log.debug("mousetype: %s, disk_bus: %s, disk_dev: %s", self.mousetype, self.disk_bus, self.disk_dev)
        self.log.debug("icicletmp: %s, listen_port: %d", self.icicle_tmp, self.listen_port)
        self.log.debug("console_listen_port: %s", self.console_listen_port)

    def image_name(self):
        """
        Name of the image being built.
        """
        return self.name

    def output_image_path(self):
        """
        Path to the created image file.
        """
        return self.diskimage

    def get_auto_path(self):
        """
        Base method used to generate the path to the automatic installation
        file (kickstart, preseed, winnt.sif, etc).  Some subclasses override
        override this method to provide support for additional aliases.
        """
        return oz.ozutil.generate_full_auto_path(self.tdl.distro + self.tdl.update + ".auto")

    def default_auto_file(self):
        """
        Method to determine if the auto file is the default one or
        user-provided.
        """
        return self.auto == self.get_auto_path()

    def cleanup_old_guest(self):
        """
        Method to completely clean up an old guest, including deleting the
        disk file.  Use with caution!
        """
        self.log.info("Cleaning up guest named %s", self.tdl.name)
        try:
            dom = self.libvirt_conn.lookupByName(self.tdl.name)
            try:
                dom.destroy()
            except libvirt.libvirtError:
                pass
            dom.undefine()
        except libvirt.libvirtError:
            pass

        try:
            os.unlink(self.diskimage)
        except OSError as err:
            if err.errno != errno.ENOENT:
                raise

    def check_for_guest_conflict(self):
        """
        Method to check if any of our future actions will conflict with an
        already existing guest.  In particular, if a guest with the same
        name, UUID, or diskimage already exists, this throws an exception.
        """
        self.log.info("Checking for guest conflicts with %s", self.tdl.name)

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

    def generate_install_media(self, force_download=False,
                               customize_or_icicle=False):
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

    def _generate_serial_xml(self, devices):
        """
        Method to generate the serial portion of the libvirt XML.
        """
        serial = oz.ozutil.lxml_subelement(devices, "serial", None, {'type': 'tcp'})
        oz.ozutil.lxml_subelement(serial, "source", None,
                                  {'mode': 'bind', 'host': '127.0.0.1', 'service': str(self.listen_port)})
        oz.ozutil.lxml_subelement(serial, "protocol", None, {'type': 'raw'})
        target = oz.ozutil.lxml_subelement(serial, "target", None, {'port': '1'})
        if self.tdl.arch == 's390x':
            # use a different console, as sclp can be used as most once
            target.set('type', 'sclp-serial')
            oz.ozutil.lxml_subelement(target, "model", None, {'name': 'sclplmconsole'})

    def _generate_virtio_channel(self, devices, name):
        """
        Method to generate libvirt XML for a virtio channel.
        """
        virtio = oz.ozutil.lxml_subelement(devices, "channel", None, {'type': 'tcp'})
        oz.ozutil.lxml_subelement(virtio, "source", None,
                                  {'mode': 'bind', 'host': '127.0.0.1', 'service': str(self.console_listen_port)})
        oz.ozutil.lxml_subelement(virtio, "target", None, {"type": "virtio", "name": name})

    def _generate_xml(self, bootdev, installdev, kernel=None, initrd=None,
                      cmdline=None, virtio_channel_name=None):
        """
        Method to generate libvirt XML useful for installation.
        """
        self.log.info("Generate XML for guest %s with bootdev %s", self.tdl.name, bootdev)

        # top-level domain element
        domain = lxml.etree.Element("domain", type=self.libvirt_type)
        # name element
        oz.ozutil.lxml_subelement(domain, "name", self.tdl.name)
        # memory elements
        oz.ozutil.lxml_subelement(domain, "memory", str(self.install_memory))
        oz.ozutil.lxml_subelement(domain, "currentMemory", str(self.install_memory))
        # uuid
        oz.ozutil.lxml_subelement(domain, "uuid", str(self.uuid))
        # clock offset
        oz.ozutil.lxml_subelement(domain, "clock", None, {'offset': self.clockoffset})
        # vcpu
        oz.ozutil.lxml_subelement(domain, "vcpu", str(self.install_cpus))
        # features
        features = oz.ozutil.lxml_subelement(domain, "features")
        if self.tdl.arch in ["aarch64", "x86_64"]:
            oz.ozutil.lxml_subelement(features, "acpi")
        if self.tdl.arch in ["x86_64"]:
            oz.ozutil.lxml_subelement(features, "apic")
            oz.ozutil.lxml_subelement(features, "pae")
        if self.tdl.arch in ["armv7l"]:
            oz.ozutil.lxml_subelement(features, "gic", attributes={'version': '2'})
        # CPU
        if self.tdl.arch in ["aarch64", "armv7l"] and self.libvirt_type == "kvm":
            # Possibly related to RHBZ 1171501 - need host passthrough for aarch64 and arm with kvm
            cpu = oz.ozutil.lxml_subelement(domain, "cpu", None, {'mode': 'custom', 'match': 'exact'})
            oz.ozutil.lxml_subelement(cpu, "model", "host", {'fallback': 'allow'})
        # os
        osNode = oz.ozutil.lxml_subelement(domain, "os")
        mods = None
        if self.tdl.arch in ["aarch64", "armv7l"]:
            mods = {'arch': self.tdl.arch, 'machine': 'virt'}
        oz.ozutil.lxml_subelement(osNode, "type", "hvm", mods)
        if bootdev:
            oz.ozutil.lxml_subelement(osNode, "boot", None, {'dev': bootdev})
        if kernel:
            oz.ozutil.lxml_subelement(osNode, "kernel", kernel)
        if initrd:
            oz.ozutil.lxml_subelement(osNode, "initrd", initrd)
        if cmdline:
            oz.ozutil.lxml_subelement(osNode, "cmdline", cmdline)
        if self.tdl.arch == "aarch64":
            loader, nvram = oz.ozutil.find_uefi_firmware(self.tdl.arch)
            oz.ozutil.lxml_subelement(osNode, "loader", loader, {'readonly': 'yes', 'type': 'pflash'})
            oz.ozutil.lxml_subelement(osNode, "nvram", None, {'template': nvram})
        # poweroff, reboot, crash
        oz.ozutil.lxml_subelement(domain, "on_poweroff", "destroy")
        oz.ozutil.lxml_subelement(domain, "on_reboot", "destroy")
        oz.ozutil.lxml_subelement(domain, "on_crash", "destroy")
        # devices
        devices = oz.ozutil.lxml_subelement(domain, "devices")
        # graphics
        if self.tdl.arch not in ["aarch64", "armv7l", "s390x"]:
            # qemu for arm/aarch64/s390x does not support a graphical console - amazingly
            oz.ozutil.lxml_subelement(devices, "graphics", None, {'port': '-1', 'type': 'vnc'})
        # network
        interface = oz.ozutil.lxml_subelement(devices, "interface", None, {'type': 'bridge'})
        oz.ozutil.lxml_subelement(interface, "source", None, {'bridge': self.bridge_name})
        oz.ozutil.lxml_subelement(interface, "mac", None, {'address': self.macaddr})
        oz.ozutil.lxml_subelement(interface, "model", None, {'type': self.nicmodel})
        # input
        mousedict = {'bus': self.mousetype}
        if self.mousetype == "ps2":
            mousedict['type'] = 'mouse'
        elif self.mousetype == "usb":
            mousedict['type'] = 'tablet'
        oz.ozutil.lxml_subelement(devices, "input", None, mousedict)
        # serial console pseudo TTY
        console = oz.ozutil.lxml_subelement(devices, "serial", None, {'type': 'pty'})
        oz.ozutil.lxml_subelement(console, "target", None, {'port': '0'})
        # serial
        self._generate_serial_xml(devices)
        # virtio
        if virtio_channel_name is not None:
            self._generate_virtio_channel(devices, virtio_channel_name)
            self.has_consolelog = True
        else:
            self.has_consolelog = False
        # virtio-rng
        virtioRNG = oz.ozutil.lxml_subelement(devices, "rng", None, {'model': 'virtio'})
        oz.ozutil.lxml_subelement(virtioRNG, "rate", None, {'bytes': '1024', 'period': '1000'})
        oz.ozutil.lxml_subelement(virtioRNG, "backend", "/dev/random", {'model': 'random'})
        # boot disk
        bootDisk = oz.ozutil.lxml_subelement(devices, "disk", None, {'device': 'disk', 'type': 'file'})
        oz.ozutil.lxml_subelement(bootDisk, "target", None, {'dev': self.disk_dev, 'bus': self.disk_bus})
        oz.ozutil.lxml_subelement(bootDisk, "source", None, {'file': self.diskimage})
        oz.ozutil.lxml_subelement(bootDisk, "driver", None, {'name': 'qemu', 'type': self.image_type})
        # install disk (if any)
        if not installdev:
            installdev_list = []
        elif not isinstance(installdev, list):
            installdev_list = [installdev]
        else:
            installdev_list = installdev
        for idev in installdev_list:
            install = oz.ozutil.lxml_subelement(devices, "disk", None, {'type': 'file', 'device': idev.devicetype})
            oz.ozutil.lxml_subelement(install, "source", None, {'file': idev.path})
            oz.ozutil.lxml_subelement(install, "target", None, {'dev': idev.bus})

        xml = lxml.etree.tostring(domain, pretty_print=True, encoding="unicode")
        self.log.debug("Generated XML:\n%s", xml)

        return xml

    def _internal_generate_diskimage(self, size=10, force=False,
                                     create_partition=False,
                                     image_filename=None,
                                     backing_filename=None):
        """
        Internal method to generate a diskimage.
        Set image_filename to override the default selection of self.diskimage
        Set backing_filename to force diskimage to be a writeable qcow2 snapshot
        backed by "backing_filename" which can be either a raw image or a
        qcow2 image.
        """
        if not force and os.access(self.jeos_filename, os.F_OK):
            # if we found a cached JEOS, we don't need to do anything here;
            # we'll copy the JEOS itself later on
            return

        self.log.info("Generating %dGB diskimage for %s", size, self.tdl.name)

        diskimage = self.diskimage
        if image_filename:
            diskimage = image_filename

        directory = os.path.dirname(diskimage)
        filename = os.path.basename(diskimage)

        # create the pool XML
        pool = lxml.etree.Element("pool", type="dir")
        oz.ozutil.lxml_subelement(pool, "name", "oztempdir" + str(uuid.uuid4()))
        target = oz.ozutil.lxml_subelement(pool, "target")
        oz.ozutil.lxml_subelement(target, "path", directory)
        pool_xml = lxml.etree.tostring(pool, pretty_print=True, encoding="unicode")

        # create the volume XML
        vol = lxml.etree.Element("volume", type="file")
        oz.ozutil.lxml_subelement(vol, "name", filename)
        oz.ozutil.lxml_subelement(vol, "allocation", "0")
        target = oz.ozutil.lxml_subelement(vol, "target")
        imgtype = self.image_type
        if backing_filename:
            # Only qcow2 supports image creation using a backing file
            imgtype = "qcow2"
        oz.ozutil.lxml_subelement(target, "format", None, {"type": imgtype})

        # FIXME: this makes the permissions insecure, but is needed since
        # libvirt launches guests as qemu:qemu
        permissions = oz.ozutil.lxml_subelement(target, "permissions")
        oz.ozutil.lxml_subelement(permissions, "mode", "0666")

        capacity = size
        if backing_filename:
            # FIXME: Revisit as RHBZ 958510 evolves
            # At the moment libvirt forces us to specify a size rather than
            # assuming we want to inherit the size of our backing file.
            # It may be possible to avoid this inspection step if libvirt
            # allows creation without an explicit capacity element.
            qcow_size = oz.ozutil.check_qcow_size(backing_filename)
            if qcow_size:
                capacity = qcow_size / 1024 / 1024 / 1024
                backing_format = 'qcow2'
            else:
                capacity = os.path.getsize(backing_filename) / 1024 / 1024 / 1024
                backing_format = 'raw'
            backing = oz.ozutil.lxml_subelement(vol, "backingStore")
            oz.ozutil.lxml_subelement(backing, "path", backing_filename)
            oz.ozutil.lxml_subelement(backing, "format", None,
                                      {"type": backing_format})

        oz.ozutil.lxml_subelement(vol, "capacity", str(capacity), {'unit': 'G'})
        vol_xml = lxml.etree.tostring(vol, pretty_print=True, encoding="unicode")

        # sigh.  Yes, this is racy; if a pool is defined during this loop, we
        # might miss it.  I'm not quite sure how to do it better, and in any
        # case we don't expect that to happen often
        started = False
        found = False
        for poolname in self.libvirt_conn.listDefinedStoragePools() + self.libvirt_conn.listStoragePools():
            pool = self.libvirt_conn.storagePoolLookupByName(poolname)
            doc = lxml.etree.fromstring(pool.XMLDesc(0))
            res = doc.xpath('/pool/target/path')
            if len(res) != 1:
                continue
            if res[0].text == directory:
                # OK, this pool manages that directory; make sure it is running
                found = True
                if not pool.isActive():
                    pool.create(0)
                    started = True
                break

        if not found:
            pool = self.libvirt_conn.storagePoolCreateXML(pool_xml, 0)
            started = True

        def _vol_create_cb(args):
            """
            The callback used for waiting on volume creation to complete.
            """
            pool = args[0]
            vol_xml = args[1]

            try:
                pool.refresh(0)
            except libvirt.libvirtError as e:
                if e.get_error_code() == libvirt.VIR_ERR_INTERNAL_ERROR:
                    # libvirt returns a VIR_ERR_INTERNAL_ERROR when the
                    # refresh fails.
                    return False
                raise

            # this is a bit complicated, because of the cases that can
            # happen.  The cases are:
            #
            # 1.  The volume did not exist.  In this case, storageVolLookupByName()
            #     throws an exception, which we just ignore.  We then go on to
            #     create the volume
            # 2.  The volume did exist.  In this case, storageVolLookupByName()
            #     returns a valid volume object, and then we delete the volume
            try:
                vol = pool.storageVolLookupByName(filename)
                vol.delete(0)
            except libvirt.libvirtError as e:
                if e.get_error_code() != libvirt.VIR_ERR_NO_STORAGE_VOL:
                    raise

            pool.createXML(vol_xml, 0)

            return True

        try:
            # libvirt will not allow us to do certain operations (like a refresh)
            # while other operations are happening on a pool (like creating a new
            # volume).  Since we don't exactly know which other processes might be
            # running on the system, we retry for a while until our refresh and
            # volume creation succeed.  In most cases these operations will be fast.
            oz.ozutil.timed_loop(90, _vol_create_cb, "Waiting for volume to be created", (pool, vol_xml))
        finally:
            if started:
                pool.destroy()

        if create_partition:
            if backing_filename:
                self.log.warning("Asked to create partition against a copy-on-write snapshot - ignoring")
            else:
                g_handle = oz.GuestFSManager.GuestFS(self.diskimage, self.image_type)
                g_handle.create_msdos_partition_table()
                g_handle.cleanup()

    def generate_diskimage(self, size=10, force=False):
        """
        Method to generate a diskimage.  By default, a blank diskimage of
        10GB will be created; the caller can override this with the size
        parameter, specified in GB.  If force is False (the default), then
        a diskimage will not be created if a cached JEOS is found.  If
        force is True, a diskimage will be created regardless of whether a
        cached JEOS exists.  See the oz-install man page for more
        information about JEOS caching.
        """
        return self._internal_generate_diskimage(size, force, False)

    def _get_disks_and_interfaces(self, libvirt_xml):
        """
        Method to figure out the disks and interfaces attached to a domain.
        The method returns two lists: the first is a list of disk devices (like
        hda, hdb, etc), and the second is a list of network devices (like vnet0,
        vnet1, etc).
        """
        doc = lxml.etree.fromstring(libvirt_xml)
        disktargets = doc.xpath("/domain/devices/disk/target")

        if len(disktargets) < 1:
            raise oz.OzException.OzException("Could not find disk target")
        disks = []
        for target in disktargets:
            dev = target.get('dev')
            if dev:
                disks.append(dev)
        if not disks:
            raise oz.OzException.OzException("Could not find disk target device")
        inttargets = doc.xpath("/domain/devices/interface/target")
        if len(inttargets) < 1:
            raise oz.OzException.OzException("Could not find interface target")
        interfaces = []
        for target in inttargets:
            dev = target.get('dev')
            if dev:
                interfaces.append(dev)
        if not interfaces:
            raise oz.OzException.OzException("Could not find interface target device")

        return disks, interfaces

    def _get_disk_and_net_activity(self, libvirt_dom, disks, interfaces):
        """
        Method to collect the disk and network activity by the domain.  The
        method returns two numbers: the first is the sum of all disk activity
        from all disks, and the second is the sum of all network traffic from
        all network devices.
        """
        total_disk_req = 0
        for dev in disks:
            rd_req, rd_bytes, wr_req, wr_bytes, errs = libvirt_dom.blockStats(dev)
            total_disk_req += rd_req + wr_req

        total_net_bytes = 0
        for dev in interfaces:
            rx_bytes, rx_packets, rx_errs, rx_drop, tx_bytes, tx_packets, tx_errs, tx_drop = libvirt_dom.interfaceStats(dev)
            total_net_bytes += rx_bytes + tx_bytes

        return total_disk_req, total_net_bytes

    def _wait_for_install_finish(self, xml, max_time):
        """
        Method to wait for an installation to finish.  This will wait around
        until either the VM has gone away (at which point it is assumed the
        install was successful), or until the timeout is reached (at which
        point it is assumed the install failed and raise an exception).
        """

        libvirt_dom = self.libvirt_conn.createXML(xml, 0)

        disks, interfaces = self._get_disks_and_interfaces(libvirt_dom.XMLDesc(0))

        self.last_disk_activity = 0
        self.last_network_activity = 0
        self.inactivity_countdown = self.inactivity_timeout
        self.saved_exception = None
        if self.has_consolelog:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(1)
            self.sock.connect(('127.0.0.1', self.console_listen_port))

        def _finish_cb(self):
            '''
            A callback for _looper to deal with waiting for a guest to finish installing.
            '''
            if self.inactivity_countdown <= 0:
                return True
            try:
                total_disk_req, total_net_bytes = self._get_disk_and_net_activity(libvirt_dom, disks, interfaces)
            except libvirt.libvirtError as e:
                # we save the exception here because we want to raise it later
                # if this was a "real" exception
                self.saved_exception = e
                return True

            # rd_req and wr_req are the *total* number of disk read requests and
            # write requests ever made for this domain.  Similarly rd_bytes and
            # wr_bytes are the total number of network bytes read or written
            # for this domain

            # we define activity as having done a read or write request on the
            # install disk, or having done at least 4KB of network transfers in
            # the last second.  The thinking is that if the installer is putting
            # bits on disk, there will be disk activity, so we should keep
            # waiting.  On the other hand, the installer might be downloading
            # bits to eventually install on disk, so we look for network
            # activity as well.  We say that transfers of at least 4KB must be
            # made, however, to try to reduce false positives from things like
            # ARP requests

            if (total_disk_req == self.last_disk_activity) and (total_net_bytes < (self.last_network_activity + 4096)):
                # if we saw no read or write requests since the last iteration,
                # decrement our activity timer
                self.inactivity_countdown -= 1
            else:
                # if we did see some activity, then we can reset the timer
                self.inactivity_countdown = self.inactivity_timeout

            self.last_disk_activity = total_disk_req
            self.last_network_activity = total_net_bytes

            if self.has_consolelog:
                try:
                    # note that we have to build the data up here, since there
                    # is no guarantee that we will get the whole write in one go
                    data = self.sock.recv(65536)
                    if data:
                        self.log.debug(data.decode('utf-8'))
                except socket.timeout:
                    # the socket times out after 1 second.  We can just fall
                    # through to the below code because it is a noop.
                    pass

            return False

        finished = oz.ozutil.timed_loop(max_time, _finish_cb, "Waiting for %s to finish installing" % (self.tdl.name), self)

        # We get here because of a libvirt exception, an absolute timeout, or
        # an I/O timeout; we sort this out below
        if not finished:
            # if we timed out, then let's make sure to take a screenshot.
            screenshot_text = self._capture_screenshot(libvirt_dom)
            raise oz.OzException.OzException("Timed out waiting for install to finish.  %s" % (screenshot_text))
        elif self.inactivity_countdown <= 0:
            # if we saw no disk or network activity in the countdown window,
            # we presume the install has hung.  Fail here
            screenshot_text = self._capture_screenshot(libvirt_dom)
            raise oz.OzException.OzException("No disk activity in %d seconds, failing.  %s" % (self.inactivity_timeout, screenshot_text))

        # We get here only if we got a libvirt exception
        if not self._wait_for_guest_shutdown(libvirt_dom):
            if self.saved_exception is not None:
                self.log.debug("Libvirt Domain Info Failed:")
                self.log.debug(" code is %d", self.saved_exception.get_error_code())
                self.log.debug(" domain is %d", self.saved_exception.get_error_domain())
                self.log.debug(" message is %s", self.saved_exception.get_error_message())
                self.log.debug(" level is %d", self.saved_exception.get_error_level())
                self.log.debug(" str1 is %s", self.saved_exception.get_str1())
                self.log.debug(" str2 is %s", self.saved_exception.get_str2())
                self.log.debug(" str3 is %s", self.saved_exception.get_str3())
                self.log.debug(" int1 is %d", self.saved_exception.get_int1())
                self.log.debug(" int2 is %d", self.saved_exception.get_int2())
                raise self.saved_exception
            else:
                # the passed in exception was None, just raise a generic error
                raise oz.OzException.OzException("Unknown libvirt error")

        self.log.info("Install of %s succeeded", self.tdl.name)

    def _wait_for_guest_shutdown(self, libvirt_dom):
        """
        Method to wait around for orderly shutdown of a running guest.  Returns
        True if the guest shutdown in the specified time, False otherwise.
        """

        def _shutdown_cb(self):
            '''
            The _looper callback to wait for the guest to shutdown.
            '''
            try:
                libvirt_dom.info()
            except libvirt.libvirtError as e:
                if e.get_error_code() == libvirt.VIR_ERR_NO_DOMAIN:
                    # Here, the guest really, truly went away cleanly.  Thus, we know this
                    # loop has successfully completed, and we can return True.
                    return True

                # In all other cases, we got some kind of exception we didn't understand.
                # Fall through to the False return, and if we don't eventually see the
                # VIR_ERR_NO_DOMAIN, we'll return False to the caller.

            return False

        return oz.ozutil.timed_loop(self.shutdown_timeout, _shutdown_cb, "Waiting for %s to finish shutdown" % (self.tdl.name), self)

    def _get_csums(self, original_url, outdir, outputfd):
        """
        Internal method to fetch the checksum file and compute the checksum
        on the downloaded data.
        """
        if self.tdl.iso_md5_url:
            url = self.tdl.iso_md5_url
            hashname = 'md5'
        elif self.tdl.iso_sha1_url:
            url = self.tdl.iso_sha1_url
            hashname = 'sha1'
        elif self.tdl.iso_sha256_url:
            url = self.tdl.iso_sha256_url
            hashname = 'sha256'
        else:
            return True

        originalname = os.path.basename(urlparse.urlparse(original_url)[2])

        csumname = os.path.join(outdir,
                                self.tdl.distro + self.tdl.update + self.tdl.arch + "-CHECKSUM")

        (csumfd, outdir) = oz.ozutil.open_locked_file(csumname)

        os.ftruncate(csumfd, 0)

        try:
            self.log.debug("Checksum requested, fetching %s file", hashname)
            oz.ozutil.http_download_file(url, csumfd, False, self.log)
        finally:
            os.close(csumfd)

        upstream_sum = getattr(oz.ozutil,
                               'get_' + hashname + 'sum_from_file')(csumname, originalname)

        os.unlink(csumname)

        if not upstream_sum:
            raise oz.OzException.OzException("Could not find checksum for original file " + originalname)

        self.log.debug("Calculating checksum of downloaded file")
        os.lseek(outputfd, 0, os.SEEK_SET)

        local_sum = getattr(hashlib, hashname)()

        buf = oz.ozutil.read_bytes_from_fd(outputfd, 4096)
        while buf != '':
            local_sum.update(buf)
            buf = oz.ozutil.read_bytes_from_fd(outputfd, 4096)

        return local_sum.hexdigest() == upstream_sum

    def _get_original_media(self, url, fd, outdir, force_download):
        """
        Method to fetch the original media from url.  If the media is already
        cached locally, the cached copy will be used instead.
        """
        self.log.info("Fetching the original media")

        info = oz.ozutil.http_get_header(url)

        if 'HTTP-Code' not in info or int(info['HTTP-Code']) >= 400 or 'Content-Length' not in info or int(info['Content-Length']) < 0:
            raise oz.OzException.OzException("Could not reach %s to fetch boot media: %r" % (url, info))

        content_length = int(info['Content-Length'])

        if content_length == 0:
            raise oz.OzException.OzException("Install media of 0 size detected, something is wrong")

        if not force_download:
            if content_length == os.fstat(fd)[stat.ST_SIZE]:
                if self._get_csums(url, outdir, fd):
                    self.log.info("Original install media available, using cached version")
                    return

                self.log.info("Original available, but checksum mis-match; re-downloading")

        # before fetching everything, make sure that we have enough
        # space on the filesystem to store the data we are about to download
        devdata = os.statvfs(outdir)
        if (devdata.f_bsize * devdata.f_bavail) < content_length:
            raise oz.OzException.OzException("Not enough room on %s for install media" % (outdir))

        # at this point we know we are going to download something.  Make
        # sure to truncate the file so no stale data is left on the end
        os.ftruncate(fd, 0)

        self.log.info("Fetching the original install media from %s", url)
        oz.ozutil.http_download_file(url, fd, True, self.log)

        filesize = os.fstat(fd)[stat.ST_SIZE]

        if filesize != content_length:
            # if the length we downloaded is not the same as what we
            # originally saw from the headers, something went wrong
            raise oz.OzException.OzException("Expected to download %d bytes, downloaded %d" % (content_length, filesize))

        if not self._get_csums(url, outdir, fd):
            raise oz.OzException.OzException("Checksum for downloaded file does not match!")

    def _capture_screenshot(self, libvirt_dom):
        """
        Method to capture a screenshot of the VM.
        """

        # First check to ensure that we've got a graphics device that would even let
        # us take a screenshot.
        domxml = libvirt_dom.XMLDesc(0)
        doc = lxml.etree.fromstring(domxml)
        graphics = doc.xpath("/domain/devices/graphics")
        if not graphics:
            return "No graphics device found, screenshot skipped"

        oz.ozutil.mkdir_p(self.screenshot_dir)
        # create a new stream
        st = libvirt_dom.connect().newStream(0)

        # start the screenshot
        mimetype = libvirt_dom.screenshot(st, 0, 0)

        if mimetype == "image/x-portable-pixmap":
            ext = ".ppm"
        elif mimetype == "image/png":
            ext = ".png"
        else:
            return "Unknown screenshot type, failed to take screenshot"

        try:
            screenshot = os.path.realpath(os.path.join(self.screenshot_dir,
                                                       self.tdl.name + "-" + str(time.time()) + ext))

            def sink(stream, buf, opaque):  # pylint: disable=unused-argument
                """
                Function that is called back from the libvirt stream.
                """
                # opaque is the open file object
                return oz.ozutil.write_bytes_to_fd(opaque, buf)

            fd = os.open(screenshot, os.O_RDWR | os.O_CREAT)
            try:
                st.recvAll(sink, fd)
            finally:
                os.close(fd)

            st.finish()
            text = "Check screenshot at %s for more detail" % (screenshot)
        except Exception:
            text = "Failed to take screenshot"

        return text

    def _modify_libvirt_xml_for_serial(self, libvirt_xml):
        """
        Internal method to take input libvirt XML (which may have been provided
        by the user) and add an appropriate serial section so that guest
        announcement works properly.
        """
        input_doc = lxml.etree.fromstring(libvirt_xml)
        serialNode = input_doc.xpath("/domain/devices/serial")

        # we first go looking through the existing <serial> elements (if any);
        # if any exist on port 1, we delete it from the working XML and re-add
        # it below
        for serial in serialNode:
            target = serial.xpath('target')
            if len(target) != 1:
                raise oz.OzException.OzException("libvirt XML has a serial port with %d target(s), it is invalid" % (len(target)))
            if target[0].get('port') == "1":
                serial.getparent().remove(serial)
                break

        # at this point, the XML should be clean of any serial port=1 entries
        # and we can add the one we want
        devices = input_doc.xpath("/domain/devices")
        devlen = len(devices)
        if devlen == 0:
            raise oz.OzException.OzException("No devices section specified, something is wrong with the libvirt XML")
        elif devlen > 1:
            raise oz.OzException.OzException("%d devices sections specified, something is wrong with the libvirt XML" % (devlen))

        self._generate_serial_xml(devices[0])

        xml = lxml.etree.tostring(input_doc, pretty_print=True, encoding="unicode")
        self.log.debug("Generated XML:\n%s", xml)
        return xml

    def _modify_libvirt_xml_diskimage(self, libvirt_xml, new_diskimage, image_type):
        """
        Internal method to take input libvirt XML and replace the existing disk
        image details with a new disk image file and, potentially, disk image
        type.  Used in safe ICICLE generation to replace the "real" disk image
        file with a temporary writeable snapshot.
        """
        self.log.debug("Modifying libvirt XML to use disk image (%s) of type (%s)", new_diskimage, image_type)
        input_doc = lxml.etree.fromstring(libvirt_xml)
        disks = input_doc.xpath("/domain/devices/disk")
        if len(disks) != 1:
            self.log.warning("Oz given a libvirt domain with more than 1 disk; using the first one parsed")

        source = disks[0].xpath('source')
        if len(source) != 1:
            raise oz.OzException.OzException("invalid <disk> entry without a source")
        source[0].set('file', new_diskimage)

        driver = disks[0].xpath('driver')
        # at the time this function was added, all boot disk device stanzas
        # have a driver section - even raw images
        if len(driver) == 1:
            driver[0].set('type', image_type)
        else:
            raise oz.OzException.OzException("Found a disk with an unexpected number of driver sections")

        xml = lxml.etree.tostring(input_doc, pretty_print=True, encoding="unicode")
        self.log.debug("Generated XML:\n%s", xml)
        return xml

    def _wait_for_guest_boot(self, libvirt_dom):
        """
        Method to wait around for a guest to boot.  Orderly guests will boot
        up and announce their presence via a TCP message; if that happens within
        the timeout, this method returns the IP address of the guest.  If that
        doesn't happen an exception is raised.
        """
        self.log.info("Waiting for guest %s to boot", self.tdl.name)

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        try:
            self.sock.settimeout(1)
            self.sock.connect(('127.0.0.1', self.listen_port))

            self.addr = None
            self.data = b''

            def _boot_cb(self):
                '''
                The _looper callback to look for the guest to boot.
                '''
                try:
                    # note that we have to build the data up here, since there
                    # is no guarantee that we will get the whole write in one go
                    self.data += self.sock.recv(8192)
                except socket.timeout:
                    # the socket times out after 1 second.  We can just fall
                    # through to the below code because it is a noop.
                    pass

                # OK, we got data back from the socket.  Check to see if it is
                # is what we expect; essentially, some up-front garbage,
                # followed by a !<ip>,<uuid>!
                # Exclude ! from the wildcard to avoid errors when receiving two
                # announce messages in the same string
                match = re.search(b"!([^!]*?,[^!]*?)!$", self.data)
                if match is not None:
                    if len(match.groups()) != 1:
                        raise oz.OzException.OzException("Guest checked in with no data")
                    split = match.group(1).split(b',')
                    if len(split) != 2:
                        raise oz.OzException.OzException("Guest checked in with bogus data")
                    self.addr = split[0]
                    uuidstr = split[1]
                    try:
                        # use socket.inet_aton() to validate the IP address
                        socket.inet_aton(self.addr.decode('utf-8'))
                    except socket.error:
                        raise oz.OzException.OzException("Guest checked in with invalid IP address")

                    if uuidstr.decode('utf-8') != str(self.uuid):
                        raise oz.OzException.OzException("Guest checked in with unknown UUID")
                    return True

                # if the data we got didn't match, we need to continue waiting.
                # before going to sleep, make sure that the domain is still
                # around
                libvirt_dom.info()

                return False

            oz.ozutil.timed_loop(self.boot_timeout, _boot_cb, "Waiting for %s to finish boot" % (self.tdl.name), self)

        finally:
            self.sock.close()

        if self.addr is None:
            raise oz.OzException.OzException("Timed out waiting for guest to boot")

        self.addr = self.addr.decode('utf-8')
        self.log.debug("IP address of guest is %s", self.addr)

        return self.addr

    def _output_icicle_xml(self, lines, description, extra=None):
        """
        Generate ICICLE XML based on the data supplied.  The parameter 'lines'
        is expected to be an list of strings, with one package per list item.
        The parameter 'description' is a description of the guest.  The
        parameter 'extra' is an optional one that describes any additional
        information the user wanted in the ICICLE output.
        """
        icicle = lxml.etree.Element("icicle")
        if description is not None:
            oz.ozutil.lxml_subelement(icicle, "description", description)
        packages = oz.ozutil.lxml_subelement(icicle, "packages")

        for index, line in enumerate(lines):
            if line == "":
                continue
            package = oz.ozutil.lxml_subelement(packages, "package", None,
                                                {'name': line})
            if extra is not None:
                oz.ozutil.lxml_subelement(package, "extra", extra[index])

        return lxml.etree.tostring(icicle, pretty_print=True, encoding="unicode")

    def _check_url(self, iso=True, url=True):
        """
        Method to check that a TDL URL meets the requirements for a particular
        operating system.
        """

        # this method is *slightly* odd in that it references ISOs from the
        # generic Guest class.  However, the installtype comes from the user
        # TDL, which means that they could have specified an ISO installtype for
        # a floppy guest (for instance).  Since we internally always set
        # iso=False for floppy guests, this will raise an appropriate error

        if iso and self.tdl.installtype == 'iso':
            url = self.tdl.iso
        elif url and self.tdl.installtype == 'url':
            url = self.tdl.url

            # when doing URL installs, we can't allow localhost URLs (the URL
            # will be embedded into the installer, so the install is guaranteed
            # to fail with localhost URLs).  Disallow them here
            if urlparse.urlparse(url)[1] in ["localhost", "127.0.0.1",
                                             "localhost.localdomain"]:
                raise oz.OzException.OzException("Can not use localhost for an URL based install")
        else:
            if iso and url:
                raise oz.OzException.OzException("%s installs must be done via url or iso" % (self.tdl.distro))
            elif iso:
                raise oz.OzException.OzException("%s installs must be done via iso" % (self.tdl.distro))
            elif url:
                raise oz.OzException.OzException("%s installs for %s must be done via url" % (self.tdl.distro, self.tdl.arch))
            else:
                raise oz.OzException.OzException("Unknown error occurred while determining install URL")

        return url

    def _generate_openssh_key(self, privname):
        """
        Method to generate an OpenSSH compatible public/private keypair.
        """
        self.log.info("Generating new openssh key")
        pubname = privname + ".pub"
        if os.access(privname, os.F_OK) and not os.access(pubname, os.F_OK):
            # hm, private key exists but not public?  We have to regenerate
            os.unlink(privname)

        if not os.access(privname, os.F_OK) and os.access(pubname, os.F_OK):
            # hm, public key exists but not private?  We have to regenerate
            os.unlink(pubname)

        # when we get here, either both the private and public key exist, or
        # neither exist.  If they don't exist, generate them
        if not os.access(privname, os.F_OK) and not os.access(pubname, os.F_OK):
            def _null_callback(p, n, out):  # pylint: disable=unused-argument
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
            pubkey = b'\x00\x00\x00\x07' + b'ssh-rsa' + key.e + key.n

            username = os.getlogin()
            hostname = os.uname()[1]
            keystring = 'ssh-rsa %s %s@%s\n' % (base64.b64encode(pubkey).decode('utf-8'),
                                                username, hostname)

            oz.ozutil.mkdir_p(os.path.dirname(privname))
            key.save_key(privname, cipher=None)
            os.chmod(privname, 0o600)
            with open(pubname, 'w') as f:
                f.write(keystring)
            os.chmod(pubname, 0o644)


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

    def __init__(self, tdl, config, auto, output_disk, nicmodel, clockoffset,
                 mousetype, diskbus, iso_allowed, url_allowed, macaddress):
        Guest.__init__(self, tdl, config, auto, output_disk, nicmodel,
                       clockoffset, mousetype, diskbus, iso_allowed,
                       url_allowed, macaddress)

        self.orig_iso = os.path.join(self.data_dir, "isos",
                                     self.tdl.distro + self.tdl.update + self.tdl.arch + "-" + self.tdl.installtype + ".iso")
        self.modified_iso_cache = os.path.join(self.data_dir, "isos",
                                               self.tdl.distro + self.tdl.update + self.tdl.arch + "-" + self.tdl.installtype + "-oz.iso")
        self.output_iso = os.path.join(self.output_dir,
                                       self.tdl.name + "-" + self.tdl.installtype + "-oz.iso")
        self.iso_contents = os.path.join(self.data_dir, "isocontent",
                                         self.tdl.name + "-" + self.tdl.installtype)
        # An optional floppy disk to be used for installation
        self.output_floppy = os.path.join(self.output_dir,
                                          self.tdl.name + "-" + self.tdl.installtype + "-oz.img")

        self.log.debug("Original ISO path: %s", self.orig_iso)
        self.log.debug("Modified ISO cache: %s", self.modified_iso_cache)
        self.log.debug("Output ISO path: %s", self.output_iso)
        self.log.debug("ISO content path: %s", self.iso_contents)

    def _get_original_iso(self, isourl, fd, outdir, force_download):
        """
        Method to fetch the original ISO for an operating system.
        """
        self._get_original_media(isourl, fd, outdir, force_download)

    def _copy_iso(self):
        """
        Method to copy the data out of an ISO onto the local filesystem.
        """
        self.log.info("Copying ISO contents for modification")
        try:
            shutil.rmtree(self.iso_contents)
        except OSError as err:
            if err.errno != errno.ENOENT:
                raise
        os.makedirs(self.iso_contents)

        self.log.info("Setting up guestfs handle for %s", self.tdl.name)
        gfs = guestfs.GuestFS()
        self.log.debug("Adding ISO image %s", self.orig_iso)
        gfs.add_drive_opts(self.orig_iso, readonly=1, format='raw')
        self.log.debug("Launching guestfs")
        gfs.launch()
        try:
            self.log.debug("Mounting ISO")
            gfs.mount_options('ro', "/dev/sda", "/")

            self.log.debug("Checking if there is enough space on the filesystem")
            isostat = gfs.statvfs("/")
            outputstat = os.statvfs(self.iso_contents)
            if (outputstat.f_bsize * outputstat.f_bavail) < (isostat['blocks'] * isostat['bsize']):
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

                        # Make sure tar is fully done with the archive before
                        # we can continue.
                        tar.wait()
                        if tar.returncode:
                            self.log.debug('tar stdout: %s', stdouttmp.read())
                            self.log.debug('tar stderr: %s', stderrtmp.read())
                            raise oz.OzException.OzException("Tar exited with an error")

                    finally:
                        stdouttmp.close()
                        stderrtmp.close()
                finally:
                    os.close(rd)
                    os.close(wr)

                # since we extracted from an ISO, there are no write bits on
                # any of the directories.  Fix that here.
                oz.ozutil.recursively_add_write_bit(self.iso_contents)
            finally:
                os.chdir(current)
        finally:
            gfs.sync()
            gfs.umount_all()
            gfs.kill_subprocess()

    def _get_primary_volume_descriptor(self, cdfd):
        """
        Method to extract the primary volume descriptor from a CD.
        """
        # check out the primary volume descriptor to make sure it is sane
        cdfd.seek(16 * 2048)
        fmt = b"=B5sBB32s32sQLL32sHHHH"
        (desc_type, identifier, version, unused1, system_identifier,
         volume_identifier, unused2, space_size_le, space_size_be_unused,
         unused3, set_size_le, set_size_be, seqnum_le,
         seqnum_be) = struct.unpack(fmt, cdfd.read(struct.calcsize(fmt)))

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
        if cdfile is None:
            raise oz.OzException.OzException("input iso is None")
        if outfile is None:
            raise oz.OzException.OzException("output file is None")

        with open(cdfile, 'rb') as cdfd:
            self._get_primary_volume_descriptor(cdfd)

            # the 17th sector contains the boot specification and the offset of the
            # boot sector
            cdfd.seek(17 * 2048)

            # NOTE: With "native" alignment (the default for struct), there is
            # some padding that happens that causes the unpacking to fail.
            # Instead we force "standard" alignment, which has no padding
            fmt = "=B5sB23s41sI"
            (boot, isoIdent, version, toritoSpec, unused, bootP) = struct.unpack(fmt,
                                                                                 cdfd.read(struct.calcsize(fmt)))
            if boot != 0x0:
                raise oz.OzException.OzException("invalid CD boot sector")
            if isoIdent != "CD001":
                raise oz.OzException.OzException("invalid CD isoIdentification")
            if version != 0x1:
                raise oz.OzException.OzException("invalid CD version")
            if toritoSpec != "EL TORITO SPECIFICATION":
                raise oz.OzException.OzException("invalid CD torito specification")

            # OK, this looks like a bootable CD.  Seek to the boot sector, and
            # look for the header, 0x55, and 0xaa in the first 32 bytes
            cdfd.seek(bootP * 2048)
            fmt = "=BBH24sHBB"
            bootdata = cdfd.read(struct.calcsize(fmt))
            (header, platform, unused, manu_unused, unused2, five, aa) = struct.unpack(fmt,
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
                Method to compute the checksum on the ISO.  Note that this is *not*
                a 1's complement checksum; when an addition overflows, the carry
                bit is discarded, not added to the end.
                """
                s = 0
                for i in range(0, len(data), 2):
                    w = ord(data[i]) + (ord(data[i + 1]) << 8)
                    s = (s + w) & 0xffff
                return s

            csum = _checksum(bootdata)
            if csum != 0:
                raise oz.OzException.OzException("invalid CD checksum: expected 0, saw %d" % (csum))

            # OK, everything so far has checked out.  Read the default/initial
            # boot entry
            cdfd.seek(bootP * 2048 + 32)
            fmt = "=BBHBBHIB"
            (boot, media, loadsegment_unused, systemtype_unused, unused, scount,
             imgstart, unused2) = struct.unpack(fmt, cdfd.read(struct.calcsize(fmt)))

            if boot != 0x88:
                raise oz.OzException.OzException("invalid CD initial boot indicator")
            if unused != 0x0 or unused2 != 0x0:
                raise oz.OzException.OzException("invalid CD initial boot unused field")

            if media == 0 or media == 4:
                count = scount
            elif media == 1:
                # 1.2MB floppy in sectors
                count = 1200 * 1024 / 512
            elif media == 2:
                # 1.44MB floppy in sectors
                count = 1440 * 1024 / 512
            elif media == 3:
                # 2.88MB floppy in sectors
                count = 2880 * 1024 / 512
            else:
                raise oz.OzException.OzException("invalid CD media type")

            # finally, seek to "imgstart", and read "count" sectors, which
            # contains the boot image
            cdfd.seek(imgstart * 2048)

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
            eltoritodata = cdfd.read(count * 512)

        with open(outfile, "w") as f:
            f.write(eltoritodata)

    def _do_install(self, timeout=None, force=False, reboots=0,
                    kernelfname=None, ramdiskfname=None, cmdline=None,
                    extrainstalldevs=None, virtio_channel_name=None):
        """
        Internal method to actually run the installation.
        """
        if not force and os.access(self.jeos_filename, os.F_OK):
            self.log.info("Found cached JEOS (%s), using it", self.jeos_filename)
            oz.ozutil.copyfile_sparse(self.jeos_filename, self.diskimage)
            return self._generate_xml("hd", None)

        self.log.info("Running install for %s", self.tdl.name)

        if timeout is None:
            timeout = self.default_install_timeout

        cddev = self._InstallDev("cdrom", self.output_iso, "hdc")
        if extrainstalldevs is not None:
            extrainstalldevs.append(cddev)
            cddev = extrainstalldevs
        reboots_to_go = reboots
        while reboots_to_go >= 0:
            # if reboots_to_go is the same as reboots, it means that this is
            # the first time through and we should generate the "initial" xml
            if reboots_to_go == reboots:
                if kernelfname and os.access(kernelfname, os.F_OK) and ramdiskfname and os.access(ramdiskfname, os.F_OK) and cmdline:
                    xml = self._generate_xml(None, None, kernelfname,
                                             ramdiskfname, cmdline,
                                             virtio_channel_name)
                else:
                    xml = self._generate_xml("cdrom", cddev, None, None, None,
                                             virtio_channel_name)
            else:
                xml = self._generate_xml("hd", cddev, None, None, None,
                                         virtio_channel_name)

            self._wait_for_install_finish(xml, timeout)

            reboots_to_go -= 1

        if self.cache_jeos:
            self.log.info("Caching JEOS")
            oz.ozutil.mkdir_p(self.jeos_cache_dir)
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

    def _check_iso_tree(self, customize_or_icicle):
        """
        Base method to check the exploded ISO tree.  In the common case, do
        nothing; subclasses that need to check the tree will override this.
        """
        pass

    def _add_iso_extras(self):
        """
        Method to modify the ISO based on the directories specified in the TDL
        file. This modification is done before the final OS and is not
        expected to be override by subclasses
        """
        for isoextra in self.tdl.isoextras:
            targetabspath = os.path.join(self.iso_contents,
                                         isoextra.destination)
            oz.ozutil.mkdir_p(os.path.dirname(targetabspath))

            parsedurl = urlparse.urlparse(isoextra.source)
            if parsedurl.scheme == 'file':
                if isoextra.element_type == "file":
                    oz.ozutil.copyfile_sparse(parsedurl.path, targetabspath)
                else:
                    oz.ozutil.copytree_merge(parsedurl.path, targetabspath)
            elif parsedurl.scheme == "ftp":
                if isoextra.element_type == "file":
                    fd = os.open(targetabspath,
                                 os.O_CREAT | os.O_TRUNC | os.O_WRONLY)
                    try:
                        oz.ozutil.http_download_file(isoextra.source, fd, True,
                                                     self.log)
                    finally:
                        os.close(fd)
                else:
                    oz.ozutil.ftp_download_directory(parsedurl.hostname,
                                                     parsedurl.username,
                                                     parsedurl.password,
                                                     parsedurl.path,
                                                     targetabspath,
                                                     parsedurl.port)
            elif parsedurl.scheme == "http":
                if isoextra.element_type == "directory":
                    raise oz.OzException.OzException("ISO extra directories cannot be fetched over HTTP")
                else:
                    fd = os.open(targetabspath,
                                 os.O_CREAT | os.O_TRUNC | os.O_WRONLY)
                    try:
                        oz.ozutil.http_download_file(isoextra.source, fd, True,
                                                     self.log)
                    finally:
                        os.close(fd)
            else:
                raise oz.OzException.OzException("The protocol '%s' is not supported for fetching remote files or directories" % parsedurl.scheme)

    def _modify_iso(self):
        """
        Base method to modify the ISO.  Subclasses are expected to override
        this.
        """
        raise oz.OzException.OzException("Internal error, subclass didn't override modify_iso")

    def _generate_new_iso(self):
        """
        Base method to generate the new ISO.  Subclasses are expected to
        override this.
        """
        raise oz.OzException.OzException("Internal error, subclass didn't override generate_new_iso")

    def _iso_generate_install_media(self, url, force_download,
                                    customize_or_icicle):
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

        (fd, outdir) = oz.ozutil.open_locked_file(self.orig_iso)

        try:
            self._get_original_iso(url, fd, outdir, force_download)
            self._check_pvd()
            self._copy_iso()

            # from here on out, we have to make sure to cleanup the exploded ISO
            try:
                self._check_iso_tree(customize_or_icicle)
                self._add_iso_extras()
                self._modify_iso()
                self._generate_new_iso()
                if self.cache_modified_media:
                    self.log.info("Caching modified media for future use")
                    shutil.copyfile(self.output_iso, self.modified_iso_cache)
            finally:
                self._cleanup_iso()
        finally:
            os.close(fd)

    def generate_install_media(self, force_download=False,
                               customize_or_icicle=False):
        """
        Method to generate the install media for the operating
        system.  If force_download is False (the default), then the
        original media will only be fetched if it is not cached locally.  If
        force_download is True, then the original media will be downloaded
        regardless of whether it is cached locally.
        """
        return self._iso_generate_install_media(self.url, force_download,
                                                customize_or_icicle)

    def _cleanup_iso(self):
        """
        Method to cleanup the local ISO contents.
        """
        self.log.info("Cleaning up old ISO data")
        # if we are running as non-root, then there might be some files left
        # around that are not writable, which means that the rmtree below would
        # fail.  Recurse into the iso_contents tree, doing a chmod +w on
        # every file and directory to make sure the rmtree succeeds
        oz.ozutil.recursively_add_write_bit(self.iso_contents)

        oz.ozutil.rmtree_and_sync(self.iso_contents)

    def cleanup_install(self):
        """
        Method to cleanup any transient install data.
        """
        self.log.info("Cleaning up after install")

        try:
            os.unlink(self.output_iso)
        except:
            pass

        try:
            os.unlink(self.output_floppy)
        except:
            pass

        if not self.cache_original_media:
            try:
                os.unlink(self.orig_iso)
            except:
                pass


class FDGuest(Guest):
    """
    Class for guest installation via floppy disk.
    """
    def __init__(self, tdl, config, auto, output_disk, nicmodel, clockoffset,
                 mousetype, diskbus, macaddress):
        Guest.__init__(self, tdl, config, auto, output_disk, nicmodel,
                       clockoffset, mousetype, diskbus, False, True, macaddress)
        self.orig_floppy = os.path.join(self.data_dir, "floppies",
                                        self.tdl.distro + self.tdl.update + self.tdl.arch + ".img")
        self.modified_floppy_cache = os.path.join(self.data_dir, "floppies",
                                                  self.tdl.distro + self.tdl.update + self.tdl.arch + "-oz.img")
        self.output_floppy = os.path.join(self.output_dir,
                                          self.tdl.name + "-oz.img")
        self.floppy_contents = os.path.join(self.data_dir, "floppycontent",
                                            self.tdl.name)

        self.log.debug("Original floppy path: %s", self.orig_floppy)
        self.log.debug("Modified floppy cache: %s", self.modified_floppy_cache)
        self.log.debug("Output floppy path: %s", self.output_floppy)
        self.log.debug("Floppy content path: %s", self.floppy_contents)

    def _get_original_floppy(self, floppyurl, fd, outdir, force_download):
        """
        Method to download the original floppy if necessary.
        """
        self._get_original_media(floppyurl, fd, outdir, force_download)

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
            return self._generate_xml("hd", None)

        self.log.info("Running install for %s", self.tdl.name)

        fddev = self._InstallDev("floppy", self.output_floppy, "fda")

        if timeout is None:
            timeout = 1200

        self._wait_for_install_finish(self._generate_xml("fd", fddev), timeout)

        if self.cache_jeos:
            self.log.info("Caching JEOS")
            oz.ozutil.mkdir_p(self.jeos_cache_dir)
            oz.ozutil.copyfile_sparse(self.diskimage, self.jeos_filename)

        return self._generate_xml("hd", None)

    def _cleanup_floppy(self):
        """
        Method to cleanup the temporary floppy data.
        """
        self.log.info("Cleaning up floppy data")
        oz.ozutil.rmtree_and_sync(self.floppy_contents)

    def cleanup_install(self):
        """
        Method to cleanup the installation floppies.
        """
        self.log.info("Cleaning up after install")
        try:
            os.unlink(self.output_floppy)
        except:
            pass

        if not self.cache_original_media:
            try:
                os.unlink(self.orig_floppy)
            except Exception:
                pass
