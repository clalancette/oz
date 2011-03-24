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

import os
import re
import shutil

import Guest
import ozutil
import OzException

class RHEL21Guest(Guest.FDGuest):
    def __init__(self, tdl, config, auto):
        Guest.FDGuest.__init__(self, tdl.name, tdl.distro, tdl.update,
                               tdl.arch, "pcnet", None, None, None, config)

        self.tdl = tdl
        if self.tdl.arch != "i386":
            raise OzException.OzException("Invalid arch " + self.tdl.arch + "for RHEL-2.1 guest")

        self.ks_file = auto
        if self.ks_file is None:
            self.ks_file = ozutil.generate_full_auto_path("rhel-2.1-jeos.ks")

        self.url = self.check_url(self.tdl, iso=False, url=True)

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
        lines.append("  append initrd=initrd.img lang= devfs=nomount ramdisk_dize=9216 ks=floppy method=" + self.url + "\n")

        f = open(syslinux, "w")
        f.writelines(lines)
        f.close()

        Guest.subprocess_check_output(["mcopy", "-n", "-o", "-i",
                                       self.output_floppy, syslinux,
                                       "::SYSLINUX.CFG"])

    def generate_install_media(self, force_download=False):
        self.log.info("Generating install media")

        if not force_download and os.access(self.modified_floppy_cache,
                                            os.F_OK):
            self.log.info("Using cached modified media")
            shutil.copyfile(self.modified_floppy_cache, self.output_floppy)
            return

        self.get_original_floppy(self.url + "/images/bootnet.img",
                                 force_download)
        self.copy_floppy()
        try:
            self.modify_floppy()
            if self.cache_modified_media:
                self.log.info("Caching modified media for future use")
                shutil.copyfile(self.output_floppy, self.modified_floppy_cache)
        finally:
            self.cleanup_floppy()

def get_class(tdl, config, auto):
    if tdl.update in ["GOLD", "U2", "U3", "U4", "U5", "U6"]:
        return RHEL21Guest(tdl, config, auto)
    raise OzException.OzException("Unsupported RHEL-2.1 update " + tdl.update)
