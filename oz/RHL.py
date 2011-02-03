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

import re
import shutil
import os

import Guest
import ozutil
import RedHat

class RHL9Guest(Guest.CDGuest):
    def __init__(self, tdl, config, auto):
        self.tdl = tdl

        self.ks_file = auto
        if self.ks_file is None:
            self.ks_file = ozutil.generate_full_auto_path("rhl-" + self.tdl.update + "-jeos.ks")

        if self.tdl.installtype != 'url':
            raise Guest.OzException("RHL installs must be done via url")

        ozutil.deny_localhost(self.tdl.url)

        if self.tdl.arch != "i386":
            raise Guest.OzException("Invalid arch " + self.tdl.arch + "for RHL guest")

        Guest.CDGuest.__init__(self, self.tdl.name, "RHL", "9", "i386", "url",
                               "rtl8139", None, None, None, config)

    def modify_iso(self):
        self.log.debug("Putting the kickstart in place")

        output_ks = os.path.join(self.iso_contents, "ks.cfg")
        shutil.copyfile(self.ks_file, output_ks)
        f = open(output_ks, "r")
        lines = f.readlines()
        f.close()

        for line in lines:
            if re.match("^url", line):
                lines[lines.index(line)] = "url --url " + self.tdl.url + "\n"

        f = open(output_ks, "w")
        f.writelines(lines)
        f.close()

        self.log.debug("Modifying the boot options")
        isolinuxcfg = os.path.join(self.iso_contents, "isolinux", "isolinux.cfg")
        f = open(isolinuxcfg, "r")
        lines = f.readlines()
        f.close()
        for line in lines:
            if re.match("timeout", line):
                lines[lines.index(line)] = "timeout 1\n"
            elif re.match("default", line):
                lines[lines.index(line)] = "default customiso\n"
        lines.append("label customiso\n")
        lines.append("  kernel vmlinuz\n")
        lines.append("  append initrd=initrd.img ks=cdrom:/ks.cfg method=" + self.tdl.url + "\n")

        f = open(isolinuxcfg, "w")
        f.writelines(lines)
        f.close()

    def generate_new_iso(self):
        self.log.debug("Generating new ISO")
        RedHat.generate_iso(self.output_iso, self.iso_contents)

    def generate_install_media(self, force_download):
        self.get_original_iso(self.tdl.url + "/images/boot.iso", force_download)
        self.copy_iso()
        self.modify_iso()
        self.generate_new_iso()
        self.cleanup_iso()

class RHL70and71and72and73and8Guest(Guest.FDGuest):
    def __init__(self, tdl, config, auto, nicmodel):
        self.tdl = tdl

        self.ks_file = auto
        if self.ks_file is None:
            self.ks_file = ozutil.generate_full_auto_path("rhl-" + self.tdl.update + "-jeos.ks")

        if self.tdl.installtype != 'url':
            raise Guest.OzException("RHL installs must be done via url")

        ozutil.deny_localhost(self.tdl.url)

        if self.tdl.arch != "i386":
            raise Guest.OzException("Invalid arch " + self.tdl.arch + "for RHL guest")

        Guest.FDGuest.__init__(self, self.tdl.name, "RHL", self.tdl.update,
                               "i386", nicmodel, None, None, None, config)

    def modify_floppy(self):
        self.mkdir_p(self.floppy_contents)

        self.log.debug("Putting the kickstart in place")

        output_ks = os.path.join(self.floppy_contents, "ks.cfg")
        shutil.copyfile(self.ks_file, output_ks)
        f = open(output_ks, "r")
        lines = f.readlines()
        f.close()

        for line in lines:
            if re.match("^url", line):
                lines[lines.index(line)] = "url --url " + self.tdl.url + "\n"

        f = open(output_ks, "w")
        f.writelines(lines)
        f.close()
        Guest.subprocess_check_output(["mcopy", "-i", self.output_floppy,
                                       output_ks, "::KS.CFG"])

        self.log.debug("Modifying the syslinux.cfg")

        Guest.subprocess_check_output(["mcopy", "-n", "-o", "-i",
                                       self.output_floppy, "::SYSLINUX.CFG",
                                       self.floppy_contents])
        syslinux = os.path.join(self.floppy_contents, "SYSLINUX.CFG")
        f = open(syslinux, "r")
        lines = f.readlines()
        f.close()

        for line in lines:
            if re.match("timeout", line):
                lines[lines.index(line)] = "timeout 1\n"
            if re.match("default", line):
                lines[lines.index(line)] = "default customboot\n"
        lines.append("label customboot\n")
        lines.append("  kernel vmlinuz\n")
        lines.append("  append initrd=initrd.img lang= devfs=nomount ramdisk_size=9216 ks=floppy method=" + self.tdl.url + "\n")

        f = open(syslinux, "w")
        f.writelines(lines)
        f.close()

        # sometimes, syslinux.cfg on the floppy gets marked read-only.  Avoid
        # problems with the subsequent mcopy by marking it read/write.
        Guest.subprocess_check_output(["mattrib", "-r", "-i",
                                       self.output_floppy, "::SYSLINUX.CFG"])

        Guest.subprocess_check_output(["mcopy", "-n", "-o", "-i",
                                       self.output_floppy, syslinux,
                                       "::SYSLINUX.CFG"])

    def generate_install_media(self, force_download):
        self.get_original_floppy(self.tdl.url + "/images/bootnet.img",
                                 force_download)
        self.copy_floppy()
        self.modify_floppy()
        self.cleanup_floppy()

def get_class(tdl, config, auto):
    if tdl.update in ["9"]:
        return RHL9Guest(tdl, config, auto)
    if tdl.update in ["7.2", "7.3", "8"]:
        return RHL70and71and72and73and8Guest(tdl, config, auto, "rtl8139")
    # FIXME: RHL 6.2 does not work via HTTP because of a bug in the installer;
    # when parsing a URL passed in via "method", it fails to put a / at the
    # beginning of the URL.  What this means is that when the installer goes
    # to fetch the install images via "GET path/to/netstg2.img HTTP/0.9", the
    # web server then returns an error.  To do a fully automated install, we
    # need to use an ISO, NFS or FTP install method; I could not get FTP
    # to work, but I did not try that hard
    # FIXME: RHL 6.1 fails for a different reason, namely that there is no
    # netstg2.img available in the distribution I have.  Unfortunately, I have
    # not been able to find the netstg2.img, nor an ISO of 6.1 to do an
    # alternate install.  NFS may still work here.
    # FIXME: RHL 6.0 fails for yet a different reason, a kernel panic on boot
    # The panic is:
    # VFS: Cannot open root device 08:21
    # Kernel panic: VFS: Unable to mount root fs on 08:21
    if tdl.update in ["7.0", "7.1"]:
        return RHL70and71and72and73and8Guest(tdl, config, auto, "ne2k_pci")
    raise Guest.OzException("Unsupported RHL update " + update)
