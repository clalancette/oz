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

import shutil
import re
import os

import Guest
import ozutil

class Ubuntu(Guest.CDGuest):
    def generate_new_iso(self):
        self.log.info("Generating new ISO")
        Guest.subprocess_check_output(["mkisofs", "-r", "-V", "Custom", "-J",
                                       "-l", "-b", "isolinux/isolinux.bin",
                                       "-c", "isolinux/boot.cat",
                                       "-no-emul-boot", "-boot-load-size", "4",
                                       "-cache-inodes", "-boot-info-table",
                                       "-v", "-v", "-o", self.output_iso,
                                       self.iso_contents])

    def generate_install_media(self, force_download):
        self.get_original_iso(self.tdl.iso, force_download)
        self.copy_iso()
        try:
            self.modify_iso()
            self.generate_new_iso()
        finally:
            self.cleanup_iso()

class Ubuntu810and904Guest(Ubuntu):
    def __init__(self, tdl, initrd, config, auto):
        self.tdl = tdl

        if self.tdl.installtype != 'iso':
            raise Guest.OzException("Ubuntu installs must be done via iso")

        self.preseed_file = auto
        if self.preseed_file is None:
            self.preseed_file = ozutil.generate_full_auto_path("ubuntu-" + self.tdl.update + "-jeos.preseed")

        self.initrd = initrd

        Guest.CDGuest.__init__(self, self.tdl.name, "Ubuntu", self.tdl.update,
                               self.tdl.arch, 'iso', "virtio", None, None,
                               "virtio", config)

    def modify_iso(self):
        self.log.debug("Putting the preseed file in place")

        shutil.copy(self.preseed_file, os.path.join(self.iso_contents,
                                                    "preseed",
                                                    "customiso.seed"))

        self.log.debug("Modifying text.cfg")
        textcfg = os.path.join(self.iso_contents, "isolinux", "text.cfg")
        f = open(textcfg, "r")
        lines = f.readlines()
        f.close()

        for line in lines:
            if re.match("default", line):
                lines[lines.index(line)] = "default customiso\n"
        lines.append("label customiso\n")
        lines.append("  menu label ^Customiso\n")
        lines.append("  kernel /casper/vmlinuz\n")
        lines.append("  append file=/cdrom/preseed/customiso.seed debian-installer/locale=en_US console-setup/layoutcode=us boot=casper automatic-ubiquity noprompt initrd=" + self.initrd + " ramdisk_size=14984 --\n")

        f = open(textcfg, "w")
        f.writelines(lines)
        f.close()

        self.log.debug("Modifying isolinux.cfg")
        isolinuxcfg = os.path.join(self.iso_contents, "isolinux", "isolinux.cfg")
        f = open(isolinuxcfg, "r")
        lines = f.readlines()
        f.close()

        for line in lines:
            if re.match("default", line):
                lines[lines.index(line)] = "default customiso\n"
            elif re.match("timeout", line):
                lines[lines.index(line)] = "timeout 10\n"
            elif re.match("gfxboot", line):
                lines[lines.index(line)] = ""

        f = open(isolinuxcfg, "w")
        f.writelines(lines)
        f.close()

class Ubuntu910and1004Guest(Ubuntu):
    def __init__(self, tdl, config, auto):
        self.tdl = tdl

        if self.tdl.installtype != 'iso':
            raise Guest.OzException("Ubuntu installs must be done via iso")

        self.preseed_file = auto
        if self.preseed_file is None:
            self.preseed_file = ozutil.generate_full_auto_path("ubuntu-" + self.tdl.update + "-jeos.preseed")

        Guest.CDGuest.__init__(self, self.tdl.name, "Ubuntu", self.tdl.update,
                               self.tdl.arch, 'iso', "virtio", None, None,
                               "virtio", config)

    def modify_iso(self):
        self.log.debug("Modifying ISO")

        self.log.debug("Copying preseed file")
        shutil.copy(self.preseed_file, os.path.join(self.iso_contents,
                                                    "preseed",
                                                    "customiso.seed"))

        self.log.debug("Modifying text.cfg")
        textcfg = os.path.join(self.iso_contents, "isolinux", "text.cfg")
        f = open(textcfg, "r")
        lines = f.readlines()
        f.close()

        for line in lines:
            if re.match("default", line):
                lines[lines.index(line)] = "default customiso\n"
        lines.append("label customiso\n")
        lines.append("  menu label ^Customiso\n")
        if os.path.isdir(os.path.join(self.iso_contents, "casper")):
            lines.append("  kernel /casper/vmlinuz\n")
            lines.append("  append file=/cdrom/preseed/customiso.seed debian-installer/locale=en_US console-setup/layoutcode=us boot=casper automatic-ubiquity noprompt initrd=/casper/initrd.lz ramdisk_size=14984 --\n")
        else:
            lines.append("  kernel /install/vmlinuz\n")
            lines.append("  append file=/cdrom/preseed/customiso.seed debian-installer/locale=en_US netcfg/choose_interface=auto priority=critical initrd=/install/initrd.gz --\n")

        f = open(textcfg, "w")
        f.writelines(lines)
        f.close()

        self.log.debug("Modifying isolinux.cfg")
        isolinuxcfg = os.path.join(self.iso_contents, "isolinux",
                                   "isolinux.cfg")
        f = open(isolinuxcfg, "r")
        lines = f.readlines()
        f.close()

        for line in lines:
            if re.match("default", line):
                lines[lines.index(line)] = "default customiso\n"
            elif re.match("timeout", line):
                lines[lines.index(line)] = "timeout 10\n"
            elif re.match("gfxboot", line):
                lines[lines.index(line)] = ""

        f = open(isolinuxcfg, "w")
        f.writelines(lines)
        f.close()

class Ubuntu710and8041Guest(Ubuntu):
    def __init__(self, tdl, config, auto):
        self.tdl = tdl

        if self.tdl.installtype != 'iso':
            raise Guest.OzException("Ubuntu installs must be done via iso")

        self.preseed_file = auto
        if self.preseed_file is None:
            self.preseed_file = ozutil.generate_full_auto_path("ubuntu-" + update + "-jeos.preseed")

        Guest.CDGuest.__init__(self, self.tdl.name, "Ubuntu", self.tdl.update,
                               self.tdl.arch, 'iso', "rtl8139", None, None,
                               None, config)

    def modify_iso(self):
        self.log.debug("Putting the preseed file in place")

        shutil.copy(self.preseed_file, os.path.join(self.iso_contents,
                                                    "preseed",
                                                    "customiso.seed"))

        self.log.debug("Modifying isolinux.cfg")
        isolinuxcfg = os.path.join(self.iso_contents, "isolinux", "isolinux.cfg")
        f = open(isolinuxcfg, "r")
        lines = f.readlines()
        f.close()

        for line in lines:
            if re.match(" *TIMEOUT", line, re.IGNORECASE):
                lines[lines.index(line)] = "TIMEOUT 1\n"
            elif re.match(" *DEFAULT", line, re.IGNORECASE):
                lines[lines.index(line)] = "DEFAULT customiso\n"
            elif re.match(" *GFXBOOT", line, re.IGNORECASE):
                lines[lines.index(line)] = ""
            elif re.match("^APPEND", line, re.IGNORECASE):
                lines[lines.index(line)] = ""
        lines.append("LABEL customiso\n")
        lines.append("  menu label ^Customiso\n")
        lines.append("  kernel /casper/vmlinuz\n")
        lines.append("  append file=/cdrom/preseed/customiso.seed debian-installer/locale=en_US console-setup/layoutcode=us boot=casper automatic-ubiquity noprompt initrd=/casper/initrd.gz --\n")

        f = open(isolinuxcfg, "w")
        f.writelines(lines)
        f.close()

class Ubuntu610and704Guest(Ubuntu):
    def __init__(self, tdl, config):
        self.tdl = tdl

        if self.tdl.installtype != 'iso':
            raise Guest.OzException("Ubuntu installs must be done via iso")

        self.preseed_file = auto
        if self.preseed_file is None:
            self.preseed_file = ozutil.generate_full_auto_path("ubuntu-" + update + "-jeos.preseed")

        Guest.CDGuest.__init__(self, self.tdl.name, "Ubuntu", self.tdl.update,
                               self.tdl.arch, 'iso', "rtl8139", None, None,
                               None, config)

    def modify_iso(self):
        self.log.debug("Putting the preseed file in place")
        shutil.copy(self.preseed_file, os.path.join(self.iso_contents,
                                                    "preseed",
                                                    "customiso.seed"))

        self.log.debug("Modifying isolinux.cfg")
        isolinuxcfg = os.path.join(self.iso_contents, "isolinux", "isolinux.cfg")
        f = open(isolinuxcfg, "r")
        lines = f.readlines()
        f.close()

        for line in lines:
            if re.match(" *TIMEOUT", line, re.IGNORECASE):
                lines[lines.index(line)] = "TIMEOUT 1\n"
            elif re.match(" *DEFAULT", line, re.IGNORECASE):
                lines[lines.index(line)] = "DEFAULT customiso\n"
            elif re.match(" *GFXBOOT", line, re.IGNORECASE):
                lines[lines.index(line)] = ""
            elif re.match("^APPEND", line, re.IGNORECASE):
                lines[lines.index(line)] = ""
        lines.append("LABEL customiso\n")
        lines.append("  menu label ^Customiso\n")
        lines.append("  kernel /install/vmlinuz\n")
        lines.append("  append file=/cdrom/preseed/customiso.seed locale=en_US console-setup/ask_detect=false console-setup/layoutcode=us priority=critical ramdisk_size=141876 root=/dev/ram rw initrd=/install/initrd.gz --\n")

        f = open(isolinuxcfg, "w")
        f.writelines(lines)
        f.close()

def get_class(tdl, config, auto):
    # FIXME: there are certain types of Ubuntu ISOs that do, and do not work.
    # For instance, for *some* Ubuntu releases, you must use the -alternate
    # ISO, and for some you can use either -desktop or -alternate.  We should
    # figure out which is which and give the user some feedback when we
    # can't actually succeed

    if tdl.update in ["9.10", "10.04.1"]:
        return Ubuntu910and1004Guest(tdl, config, auto)
    if tdl.update in ["8.10", "9.04"]:
        return Ubuntu810and904Guest(tdl, "/casper/initrd.gz", config, auto)
    if tdl.update in ["7.10", "8.04", "8.04.1", "8.04.2", "8.04.3", "8.04.4"]:
        return Ubuntu710and8041Guest(tdl, config, auto)
    if tdl.update in ["6.10", "7.04"]:
        return Ubuntu610and704Guest(tdl, config, auto)
    raise Guest.OzException("Unsupported Ubuntu update " + tdl.update)
