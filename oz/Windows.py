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
import parted

import oz.Guest
import oz.ozutil
import oz.OzException

class Windows(oz.Guest.CDGuest):
    def __init__(self, tdl, config):
        oz.Guest.CDGuest.__init__(self, tdl, "rtl8139", "localtime", "usb",
                                  None, config)

        if self.tdl.key is None:
            raise oz.OzException.OzException("A key is required when installing Windows")

        self.url = self.check_url(self.tdl, iso=True, url=False)

    def generate_install_media(self, force_download=False):
        return self.iso_generate_install_media(self.url, force_download)

class Windows2000andXPand2003(Windows):
    def __init__(self, tdl, config, auto):
        Windows.__init__(self, tdl, config)

        if self.tdl.update == "2000" and self.tdl.arch != "i386":
            raise oz.OzException.OzException("Windows 2000 only supports i386 architecture")

        self.siffile = auto
        if self.siffile is None:
            self.siffile = oz.ozutil.generate_full_auto_path("windows-" + self.tdl.update + "-jeos.sif")

    def generate_new_iso(self):
        self.log.debug("Generating new ISO")
        oz.Guest.subprocess_check_output(["mkisofs", "-b", "cdboot/boot.bin",
                                          "-no-emul-boot", "-boot-load-seg",
                                          "1984", "-boot-load-size", "4",
                                          "-iso-level", "2", "-J", "-l", "-D",
                                          "-N", "-joliet-long",
                                          "-relaxed-filenames", "-v", "-v",
                                          "-V", "Custom",
                                          "-o", self.output_iso,
                                          self.iso_contents])

    def generate_diskimage(self, size=10, force=False):
        if not force and os.access(self.jeos_cache_dir, os.F_OK) and os.access(self.jeos_filename, os.F_OK):
            # if we found a cached JEOS, we don't need to do anything here;
            # we'll copy the JEOS itself later on
            return

        self.log.info("Generating %dGB diskimage for %s" % (size,
                                                            self.tdl.name))

        f = open(self.diskimage, "w")
        f.truncate(size * 1024 * 1024 * 1024)
        f.close()

        if self.tdl.update == "2000":
            # If given a blank diskimage, windows 2000 stops very early in
            # install with a message:
            #
            #  Setup has determined that your computer's starupt hard disk is
            #  new or has been erased...
            #
            # To avoid that message, just create a partition table that spans
            # the entire disk
            dev = parted.Device(self.diskimage)
            disk = parted.freshDisk(dev, 'msdos')
            constraint = parted.Constraint(device=dev)
            geom = parted.Geometry(device=dev, start=1, end=2)
            #                       end=(constraint.maxSize - 1))
            partition = parted.Partition(disk=disk,
                                         type=parted.PARTITION_NORMAL,
                                         geometry=geom)
            disk.addPartition(partition=partition, constraint=constraint)
            disk.commit()

    def get_windows_arch(self, tdl_arch):
        arch = tdl_arch
        if arch == "x86_64":
            arch = "amd64"
        return arch

    def modify_iso(self):
        self.log.debug("Modifying ISO")

        os.mkdir(os.path.join(self.iso_contents, "cdboot"))
        self.geteltorito(self.orig_iso, os.path.join(self.iso_contents,
                                                     "cdboot", "boot.bin"))

        outname = os.path.join(self.iso_contents,
                               self.get_windows_arch(self.tdl.arch),
                               "winnt.sif")

        if self.siffile == oz.ozutil.generate_full_auto_path("windows-" + self.tdl.update + "-jeos.sif"):
            # if this is the oz default siffile, we modify certain parameters
            # to make installation succeed
            computername = "OZ" + str(random.randrange(1, 900000))

            def sifsub(line):
                if re.match(" *ProductKey", line):
                    return "    ProductKey=" + self.tdl.key + "\n"
                elif re.match(" *ProductID", line):
                    return "    ProductID=" + self.tdl.key + "\n"
                elif re.match(" *ComputerName", line):
                    return "    ComputerName=" + computername + "\n"
                elif re.match(" *AdminPassword", line):
                    return "    AdminPassword=" + self.rootpw + "\n"
                else:
                    return line

            self.copy_modify_file(self.siffile, outname, sifsub)
        else:
            # if the user provided their own siffile, do not override their
            # choices; the user gets to keep both pieces if something breaks
            shutil.copy(self.siffile, outname)

    def install(self, timeout=None, force=False):
        if not force and os.access(self.jeos_cache_dir, os.F_OK) and os.access(self.jeos_filename, os.F_OK):
            self.log.info("Found cached JEOS, using it")
            oz.ozutil.copyfile_sparse(self.jeos_filename, self.diskimage)
        else:
            self.log.info("Running install for %s" % (self.tdl.name))

            cddev = self.InstallDev("cdrom", self.output_iso, "hdc")

            if timeout is None:
                timeout = 3600

            dom = self.libvirt_conn.createXML(self.generate_xml("cdrom", cddev),
                                              0)
            self.wait_for_install_finish(dom, timeout)

            dom = self.libvirt_conn.createXML(self.generate_xml("hd", cddev), 0)
            self.wait_for_install_finish(dom, timeout)

            if self.cache_jeos:
                self.log.info("Caching JEOS")
                self.mkdir_p(self.jeos_cache_dir)
                oz.ozutil.copyfile_sparse(self.diskimage, self.jeos_filename)

        return self.generate_xml("hd", None)

class Windows2008and7(Windows):
    def __init__(self, tdl, config, auto):
        Windows.__init__(self, tdl, config)

        self.unattendfile = auto
        if self.unattendfile is None:
            self.unattendfile = oz.ozutil.generate_full_auto_path("windows-" + self.tdl.update + "-jeos.xml")

    def generate_new_iso(self):
        self.log.debug("Generating new ISO")
        # NOTE: Windows 2008 is very picky about which arguments to mkisofs
        # will generate a bootable CD, so modify these at your own risk
        oz.Guest.subprocess_check_output(["mkisofs", "-b", "cdboot/boot.bin",
                                          "-no-emul-boot", "-c", "BOOT.CAT",
                                          "-iso-level", "2", "-J", "-l", "-D",
                                          "-N", "-joliet-long",
                                          "-relaxed-filenames", "-v", "-v",
                                          "-V", "Custom", "-udf",
                                          "-o", self.output_iso,
                                          self.iso_contents])

    def get_windows_arch(self, tdl_arch):
        arch = "x86"
        if tdl_arch == "x86_64":
            arch = "amd64"
        return arch

    def modify_iso(self):
        self.log.debug("Modifying ISO")

        os.mkdir(os.path.join(self.iso_contents, "cdboot"))
        self.geteltorito(self.orig_iso, os.path.join(self.iso_contents,
                                                     "cdboot", "boot.bin"))

        outname = os.path.join(self.iso_contents, "autounattend.xml")

        if self.unattendfile == oz.ozutil.generate_full_auto_path("windows-" + self.tdl.update + "-jeos.xml"):
            # if this is the oz default unattend file, we modify certain
            # parameters to make installation succeed
            doc = libxml2.parseFile(self.unattendfile)
            xp = doc.xpathNewContext()
            xp.xpathRegisterNs("ms", "urn:schemas-microsoft-com:unattend")

            for component in xp.xpathEval('/ms:unattend/ms:settings/ms:component'):
                component.setProp('processorArchitecture',
                                  self.get_windows_arch(self.tdl.arch))

            keys = xp.xpathEval('/ms:unattend/ms:settings/ms:component/ms:ProductKey')
            keys[0].setContent(self.tdl.key)

            adminpw = xp.xpathEval('/ms:unattend/ms:settings/ms:component/ms:UserAccounts/ms:AdministratorPassword/ms:Value')
            adminpw[0].setContent(self.rootpw)

            autologinpw = xp.xpathEval('/ms:unattend/ms:settings/ms:component/ms:AutoLogon/ms:Password/ms:Value')
            autologinpw[0].setContent(self.rootpw)

            doc.saveFile(outname)
        else:
            # if the user provided their own unattend file, do not override
            # their choices; the user gets to keep both pieces if something
            # breaks
            shutil.copy(self.unattendfile, outname)

    def install(self, timeout=None, force=False):
        if not force and os.access(self.jeos_cache_dir, os.F_OK) and os.access(self.jeos_filename, os.F_OK):
            self.log.info("Found cached JEOS, using it")
            oz.ozutil.copyfile_sparse(self.jeos_filename, self.diskimage)
        else:
            self.log.info("Running install for %s" % (self.tdl.name))

            cddev = self.InstallDev("cdrom", self.output_iso, "hdc")

            if timeout is None:
                timeout = 6000

            dom = self.libvirt_conn.createXML(self.generate_xml("cdrom", cddev),
                                              0)
            self.wait_for_install_finish(dom, timeout)

            dom = self.libvirt_conn.createXML(self.generate_xml("hd", cddev), 0)
            self.wait_for_install_finish(dom, timeout)

            dom = self.libvirt_conn.createXML(self.generate_xml("hd", cddev), 0)
            self.wait_for_install_finish(dom, timeout)

            if self.cache_jeos:
                self.log.info("Caching JEOS")
                self.mkdir_p(self.jeos_cache_dir)
                oz.ozutil.copyfile_sparse(self.diskimage, self.jeos_filename)

        return self.generate_xml("hd", None)

def get_class(tdl, config, auto):
    if tdl.update in ["2000", "XP", "2003"]:
        return Windows2000andXPand2003(tdl, config, auto)
    if tdl.update in ["2008", "7"]:
        return Windows2008and7(tdl, config, auto)
    raise oz.OzException.OzException("Unsupported Windows update " + tdl.update)
