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
import subprocess
import os
import re
import shutil
import ozutil

class RHEL21Guest(Guest.FDGuest):
    def __init__(self, tdl, config):
        update = tdl.update()
        if tdl.arch() != "i386":
            raise Exception, "Invalid arch " + arch + "for RHEL-2.1 guest"
        self.ks_file = ozutil.generate_full_auto_path("rhel-2.1-jeos.ks")

        if tdl.installtype() != 'url':
            raise Exception, "RHEL-2.1 installs must be done via url or iso"

        self.url = tdl.url()

        ozutil.deny_localhost(self.url)

        Guest.FDGuest.__init__(self, "RHEL-2.1", update, "i386", "pcnet", None,
                               None, None, config)

    def modify_floppy(self):
        if not os.access(self.floppy_contents, os.F_OK):
            os.makedirs(self.floppy_contents)

        self.log.debug("Putting the kickstart in place")

        output_ks = self.floppy_contents + "/ks.cfg"
        shutil.copyfile(self.ks_file, output_ks)
        f = open(output_ks, "r")
        lines = f.readlines()
        f.close()

        for line in lines:
            if re.match("^url", line):
                lines[lines.index(line)] = "url --url " + self.url + "\n"

        f = open(output_ks, "w")
        f.writelines(lines)
        f.close()
        Guest.subprocess_check_output(["mcopy", "-i", self.output_floppy,
                                       output_ks, "::KS.CFG"])

        self.log.debug("Modifying the syslinux.cfg")

        Guest.subprocess_check_output(["mcopy", "-n", "-o", "-i",
                                       self.output_floppy, "::SYSLINUX.CFG",
                                       self.floppy_contents])
        f = open(self.floppy_contents + "/SYSLINUX.CFG", "r")
        lines = f.readlines()
        f.close()

        for line in lines:
            if re.match("timeout", line):
                lines[lines.index(line)] = "timeout 1\n"
            if re.match("default", line):
                lines[lines.index(line)] = "default customboot\n"
        lines.append("label customboot\n")
        lines.append("  kernel vmlinuz\n")
        lines.append("  append initrd=initrd.img lang= devfs=nomount ramdisk_dize=9216 ks=floppy method=" + self.url + "\n")

        f = open(self.floppy_contents + "/SYSLINUX.CFG", "w")
        f.writelines(lines)
        f.close()

        Guest.subprocess_check_output(["mcopy", "-n", "-o", "-i",
                                       self.output_floppy,
                                       self.floppy_contents + "/SYSLINUX.CFG",
                                       "::SYSLINUX.CFG"])

    def generate_install_media(self, force_download):
        self.log.info("Generating install media")
        self.get_original_floppy(self.url + "/images/bootnet.img", force_download)
        self.copy_floppy()
        self.modify_floppy()

def get_class(tdl, config):
    update = tdl.update()
    if update == "GOLD" or update == "U2" or update == "U3" or update == "U4" or update == "U5" or update == "U6":
        return RHEL21Guest(tdl, config)
    raise Exception, "Unsupported RHEL-2.1 update " + update
