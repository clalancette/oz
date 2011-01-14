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

import Guest
import random
import subprocess
import re
import os
import ozutil
import libxml2

def get_windows_arch(tdl_arch):
    arch = tdl_arch
    if arch == "x86_64":
        arch = "amd64"
    return arch

class Windows2000andXPand2003(Guest.CDGuest):
    def __init__(self, tdl, config):
        self.tdl = tdl

        if self.tdl.update == "2000" and self.tdl.arch != "i386":
            raise Guest.OzException("Windows 2000 only supports i386 architecture")
        if self.tdl.key is None:
            raise Guest.OzException("A key is required when installing Windows 2000, XP, or 2003")
        self.siffile = ozutil.generate_full_auto_path("windows-" + self.tdl.update + "-jeos.sif")

        if self.tdl.installtype != 'iso':
            raise Guest.OzException("Windows installs must be done via iso")

        self.winarch = get_windows_arch(self.tdl.arch)

        Guest.CDGuest.__init__(self, "Windows", self.tdl.update, self.tdl.arch,
                               'iso', 'rtl8139', "localtime", "usb", None,
                               config)

    def generate_new_iso(self):
        self.log.debug("Generating new ISO")
        Guest.subprocess_check_output(["mkisofs", "-b", "cdboot/boot.bin",
                                       "-no-emul-boot", "-boot-load-seg",
                                       "1984", "-boot-load-size", "4",
                                       "-iso-level", "2", "-J", "-l", "-D",
                                       "-N", "-joliet-long",
                                       "-relaxed-filenames", "-v", "-v",
                                       "-V", "Custom",
                                       "-o", self.output_iso, self.iso_contents])

    def modify_iso(self):
        os.mkdir(self.iso_contents + "/cdboot")
        self.geteltorito(self.orig_iso, self.iso_contents + "/cdboot/boot.bin")

        computername = "OZ" + str(random.randrange(1, 900000))

        f = open(self.siffile, "r")
        lines = f.readlines()
        f.close()

        for line in lines:
            if re.match(" *ProductKey", line):
                lines[lines.index(line)] = "    ProductKey=" + self.tdl.key + "\n"
            elif re.match(" *ProductID", line):
                lines[lines.index(line)] = "    ProductID=" + self.tdl.key + "\n"
            elif re.match(" *ComputerName", line):
                lines[lines.index(line)] = "    ComputerName=" + computername + "\n"

        f = open(self.iso_contents + "/" + self.winarch + "/winnt.sif", "w")
        f.writelines(lines)
        f.close()

    def generate_install_media(self, force_download):
        self.get_original_iso(self.tdl.iso, force_download)
        self.copy_iso()
        self.modify_iso()
        self.generate_new_iso()
        self.cleanup_iso()

    def install(self):
        self.log.info("Running install for %s" % (self.name))
        xml = self.generate_xml("cdrom")
        dom = self.libvirt_conn.createXML(xml, 0)
        self.wait_for_install_finish(dom, 1000)

        xml = self.generate_xml("hd")
        dom = self.libvirt_conn.createXML(xml, 0)
        self.wait_for_install_finish(dom, 3600)

        return self.generate_xml("hd", want_install_disk=False)

class Windows2008and7(Guest.CDGuest):
    def __init__(self, tdl, config):
        self.tdl = tdl

        if self.tdl.key is None:
            raise Guest.OzException("A key is required when installing Windows 2000, XP, or 2003")

        self.unattendfile = ozutil.generate_full_auto_path("windows-" + self.tdl.update + "-jeos.xml")

        if self.tdl.installtype != 'iso':
            raise Guest.OzException("Windows installs must be done via iso")

        self.winarch = get_windows_arch(self.tdl.arch)

        Guest.CDGuest.__init__(self, "Windows", self.tdl.update, self.tdl.arch,
                               'iso', 'rtl8139', "localtime", "usb", None,
                               config)

    def generate_new_iso(self):
        self.log.debug("Generating new ISO")
        # NOTE: Windows 2008 is very picky about which arguments to mkisofs
        # will generate a bootable CD, so modify these at your own risk
        Guest.subprocess_check_output(["mkisofs", "-b", "cdboot/boot.bin",
                                       "-no-emul-boot", "-c", "BOOT.CAT",
                                       "-iso-level", "2", "-J", "-l", "-D",
                                       "-N", "-joliet-long",
                                       "-relaxed-filenames", "-v", "-v",
                                       "-V", "Custom", "-udf",
                                       "-o", self.output_iso, self.iso_contents])

    def modify_iso(self):
        os.mkdir(self.iso_contents + "/cdboot")
        self.geteltorito(self.orig_iso, self.iso_contents + "/cdboot/boot.bin")

        doc = libxml2.parseFile(self.unattendfile)
        xp = doc.xpathNewContext()
        xp.xpathRegisterNs("ms", "urn:schemas-microsoft-com:unattend")

        for component in xp.xpathEval('/ms:unattend/ms:settings/ms:component'):
            component.setProp('processorArchitecture', self.tdl.winarch)

        keys = xp.xpathEval('/ms:unattend/ms:settings/ms:component/ms:ProductKey')

        if len(keys[0].content) == 0:
	    keys[0].freeNode()

        keys[0].setContent(self.tdl.key)

        doc.saveFile(self.iso_contents + "/autounattend.xml")

    def generate_install_media(self, force_download):
        self.get_original_iso(self.tdl.iso, force_download)
        self.copy_iso()
        self.modify_iso()
        self.generate_new_iso()
        self.cleanup_iso()

    def install(self):
        self.log.info("Running install for %s" % (self.name))
        xml = self.generate_xml("cdrom")
        dom = self.libvirt_conn.createXML(xml, 0)
        self.wait_for_install_finish(dom, 6000)

        xml = self.generate_xml("hd")
        dom = self.libvirt_conn.createXML(xml, 0)
        self.wait_for_install_finish(dom, 6000)

        xml = self.generate_xml("hd")
        dom = self.libvirt_conn.createXML(xml, 0)
        self.wait_for_install_finish(dom, 6000)

        return self.generate_xml("hd", want_install_disk=False)

def get_class(tdl, config):
    if tdl.update in ["2000", "XP", "2003"]:
        return Windows2000andXPand2003(tdl, config)
    if tdl.update in ["2008", "7"]:
        return Windows2008and7(tdl, config)
    raise Guest.OzException("Unsupported Windows update " + tdl.update)
