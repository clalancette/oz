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

import random
import re
import os
import libxml2
import shutil

import Guest
import ozutil
import OzException

def get_windows_arch(tdl_arch):
    arch = tdl_arch
    if arch == "x86_64":
        arch = "amd64"
    return arch

class Windows2000andXPand2003(Guest.CDGuest):
    def __init__(self, tdl, config, auto):
        Guest.CDGuest.__init__(self, tdl.name, tdl.distro, tdl.update, tdl.arch,
                               tdl.installtype, 'rtl8139', "localtime", "usb",
                               None, config)

        self.tdl = tdl

        if self.tdl.update == "2000" and self.tdl.arch != "i386":
            raise OzException.OzException("Windows 2000 only supports i386 architecture")
        if self.tdl.key is None:
            raise OzException.OzException("A key is required when installing Windows 2000, XP, or 2003")

        self.siffile = auto
        if self.siffile is None:
            self.siffile = ozutil.generate_full_auto_path("windows-" + self.tdl.update + "-jeos.sif")

        self.url = self.check_url(self.tdl, iso=True, url=False)

        self.winarch = get_windows_arch(self.tdl.arch)

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
        self.log.debug("Modifying ISO")

        os.mkdir(os.path.join(self.iso_contents, "cdboot"))
        self.geteltorito(self.orig_iso, os.path.join(self.iso_contents,
                                                     "cdboot", "boot.bin"))

        outname = os.path.join(self.iso_contents, self.winarch, "winnt.sif")

        if self.siffile == ozutil.generate_full_auto_path("windows-" + self.tdl.update + "-jeos.sif"):
            # if this is the oz default siffile, we modify certain parameters
            # to make installation succeed
            computername = "OZ" + str(random.randrange(1, 900000))

            infile = open(self.siffile, 'r')
            outfile = open(outname, 'w')

            for line in infile.xreadlines():
                if re.match(" *ProductKey", line):
                    outfile.write("    ProductKey=" + self.tdl.key + "\n")
                elif re.match(" *ProductID", line):
                    outfile.write("    ProductID=" + self.tdl.key + "\n")
                elif re.match(" *ComputerName", line):
                    outfile.write("    ComputerName=" + computername + "\n")
                else:
                    outfile.write(line)

            infile.close()
            outfile.close()
        else:
            # if the user provided their own siffile, do not override their
            # choices; the user gets to keep both pieces if something breaks
            shutil.copy(self.siffile, outname)

    def generate_install_media(self, force_download=False):
        return self.iso_generate_install_media(self.url, force_download)

    def install(self, timeout=None):
        self.log.info("Running install for %s" % (self.name))
        xml = self.generate_xml("cdrom")
        dom = self.libvirt_conn.createXML(xml, 0)

        if timeout is None:
            timeout = 3600

        self.wait_for_install_finish(dom, timeout)

        xml = self.generate_xml("hd")
        dom = self.libvirt_conn.createXML(xml, 0)

        self.wait_for_install_finish(dom, timeout)

        if self.cache_jeos:
            self.log.info("Caching JEOS")
            self.mkdir_p(self.jeos_cache_dir)
            ozutil.copyfile_sparse(self.diskimage, self.jeos_filename)

        return self.generate_xml("hd", want_install_disk=False)

class Windows2008and7(Guest.CDGuest):
    def __init__(self, tdl, config, auto):
        Guest.CDGuest.__init__(self, tdl.name, tdl.distro, tdl.update, tdl.arch,
                               tdl.installtype, 'rtl8139', "localtime", "usb",
                               None, config)

        self.tdl = tdl

        if self.tdl.key is None:
            raise OzException.OzException("A key is required when installing Windows 2000, XP, or 2003")

        self.unattendfile = auto
        if self.unattendfile is None:
            self.unattendfile = ozutil.generate_full_auto_path("windows-" + self.tdl.update + "-jeos.xml")

        self.url = self.check_url(self.tdl, iso=True, url=False)

        self.winarch = get_windows_arch(self.tdl.arch)

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
        self.log.debug("Modifying ISO")

        os.mkdir(os.path.join(self.iso_contents, "cdboot"))
        self.geteltorito(self.orig_iso, os.path.join(self.iso_contents,
                                                     "cdboot", "boot.bin"))

        outname = os.path.join(self.iso_contents, "autounattend.xml")

        if self.unattendfile == ozutil.generate_full_auto_path("windows-" + self.tdl.update + "-jeos.xml"):
            # if this is the oz default unattend file, we modify certain
            # parameters to make installation succeed
            doc = libxml2.parseFile(self.unattendfile)
            xp = doc.xpathNewContext()
            xp.xpathRegisterNs("ms", "urn:schemas-microsoft-com:unattend")

            for component in xp.xpathEval('/ms:unattend/ms:settings/ms:component'):
                component.setProp('processorArchitecture', self.winarch)

            keys = xp.xpathEval('/ms:unattend/ms:settings/ms:component/ms:ProductKey')
            keys[0].setContent(self.tdl.key)

            doc.saveFile(outname)
        else:
            # if the user provided their own unattend file, do not override
            # their choices; the user gets to keep both pieces if something
            # breaks
            shutil.copy(self.unattendfile, outname)

    def generate_install_media(self, force_download=False):
        return self.iso_generate_install_media(self.url, force_download)

    def install(self, timeout=None):
        self.log.info("Running install for %s" % (self.name))
        xml = self.generate_xml("cdrom")
        dom = self.libvirt_conn.createXML(xml, 0)

        if timeout is None:
            timeout = 6000

        self.wait_for_install_finish(dom, timeout)

        xml = self.generate_xml("hd")
        dom = self.libvirt_conn.createXML(xml, 0)

        self.wait_for_install_finish(dom, timeout)

        xml = self.generate_xml("hd")
        dom = self.libvirt_conn.createXML(xml, 0)
        self.wait_for_install_finish(dom, timeout)

        if self.cache_jeos:
            self.log.info("Caching JEOS")
            self.mkdir_p(self.jeos_cache_dir)
            ozutil.copyfile_sparse(self.diskimage, self.jeos_filename)

        return self.generate_xml("hd", want_install_disk=False)

def get_class(tdl, config, auto):
    if tdl.update in ["2000", "XP", "2003"]:
        return Windows2000andXPand2003(tdl, config, auto)
    if tdl.update in ["2008", "7"]:
        return Windows2008and7(tdl, config, auto)
    raise OzException.OzException("Unsupported Windows update " + tdl.update)
