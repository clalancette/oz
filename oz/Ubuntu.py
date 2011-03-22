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

import shutil
import re
import os

import oz.Guest
import oz.ozutil
import oz.OzException

class UbuntuGuest(oz.Guest.CDGuest):
    def __init__(self, tdl, config, auto, initrd, nicmodel, diskbus):
        oz.Guest.CDGuest.__init__(self, tdl, nicmodel, None, None, diskbus,
                                  config)

        self.casper_initrd = initrd

        self.preseed_file = auto
        if self.preseed_file is None:
            self.preseed_file = oz.ozutil.generate_full_auto_path("ubuntu-" + self.tdl.update + "-jeos.preseed")

        self.url = self.check_url(self.tdl, iso=True, url=False)

    def modify_iso(self):
        self.log.debug("Modifying ISO")

        self.log.debug("Copying preseed file")
        outname = os.path.join(self.iso_contents, "preseed", "customiso.seed")

        if self.preseed_file == oz.ozutil.generate_full_auto_path("ubuntu-" + self.tdl.update + "-jeos.preseed"):

            def preseed_sub(line):
                if re.match('d-i passwd/root-password password', line):
                    return 'd-i passwd/root-password password ' + self.rootpw + '\n'
                elif re.match('d-i passwd/root-password-again password', line):
                    return 'd-i passwd/root-password-again password ' + self.rootpw + '\n'
                else:
                    return line

            self.copy_modify_file(self.preseed_file, outname, preseed_sub)
        else:
            shutil.copy(self.preseed_file, outname)

        self.log.debug("Modifying isolinux.cfg")
        isolinuxcfg = os.path.join(self.iso_contents, "isolinux",
                                   "isolinux.cfg")
        os.unlink(isolinuxcfg)
        f = open(isolinuxcfg, 'w')
        f.write("default customiso\n")
        f.write("timeout 1\n")
        f.write("prompt 0\n")
        f.write("label customiso\n")
        f.write("  menu label ^Customiso\n")
        f.write("  menu default\n")
        if os.path.isdir(os.path.join(self.iso_contents, "casper")):
            f.write("  kernel /casper/vmlinuz\n")
            f.write("  append file=/cdrom/preseed/customiso.seed boot=casper automatic-ubiquity noprompt initrd=/casper/" + self.casper_initrd + "\n")
        else:
            f.write("  kernel /install/vmlinuz\n")
            f.write("  append file=/cdrom/preseed/customiso.seed debian-installer/locale=en_US console-setup/layoutcode=us netcfg/choose_interface=auto priority=critical initrd=/install/initrd.gz --\n")
        f.close()

    def generate_new_iso(self):
        self.log.info("Generating new ISO")
        oz.Guest.subprocess_check_output(["mkisofs", "-r", "-V", "Custom", "-J",
                                       "-l", "-b", "isolinux/isolinux.bin",
                                       "-c", "isolinux/boot.cat",
                                       "-no-emul-boot", "-boot-load-size", "4",
                                       "-cache-inodes", "-boot-info-table",
                                       "-v", "-v", "-o", self.output_iso,
                                       self.iso_contents])

    def generate_install_media(self, force_download=False):
        return self.iso_generate_install_media(self.url, force_download)

class Ubuntu610and704Guest(oz.Guest.CDGuest):
    def __init__(self, tdl, config, auto):
        oz.Guest.CDGuest.__init__(self, tdl, "rtl8139", None, None, None,
                                  config)

        self.preseed_file = auto
        if self.preseed_file is None:
            self.preseed_file = oz.ozutil.generate_full_auto_path("ubuntu-" + self.tdl.update + "-jeos.preseed")

        self.url = self.check_url(self.tdl, iso=True, url=False)

    def modify_iso(self):
        self.log.debug("Putting the preseed file in place")

        outname = os.path.join(self.iso_contents, "preseed", "customiso.seed")

        if self.preseed_file == oz.ozutil.generate_full_auto_path("ubuntu-" + self.tdl.update + "-jeos.preseed"):

            def preseed_sub(line):
                if re.match('d-i passwd/root-password password', line):
                    return 'd-i passwd/root-password password ' + self.rootpw + '\n'
                elif re.match('d-i passwd/root-password-again password', line):
                    return 'd-i passwd/root-password-again password ' + self.rootpw + '\n'
                else:
                    return line

            self.copy_modify_file(self.preseed_file, outname, preseed_sub)
        else:
            shutil.copy(self.preseed_file, outname)

        self.log.debug("Modifying isolinux.cfg")
        isolinuxcfg = os.path.join(self.iso_contents, "isolinux",
                                   "isolinux.cfg")
        f = open(isolinuxcfg, "r")
        lines = f.readlines()
        f.close()

        for index, line in enumerate(lines):
            if re.match(" *TIMEOUT", line, re.IGNORECASE):
                lines[index] = "TIMEOUT 1\n"
            elif re.match(" *DEFAULT", line, re.IGNORECASE):
                lines[index] = "DEFAULT customiso\n"
            elif re.match(" *GFXBOOT", line, re.IGNORECASE):
                lines[index] = ""
            elif re.match("^APPEND", line, re.IGNORECASE):
                lines[index] = ""
        lines.append("LABEL customiso\n")
        lines.append("  menu label ^Customiso\n")
        if os.path.isdir(os.path.join(self.iso_contents, "casper")):
            lines.append("  kernel /casper/vmlinuz\n")
            lines.append("  append file=/cdrom/preseed/customiso.seed locale=en_US console-setup/ask_detect=false console-setup/layoutcode=us priority=critical ramdisk_size=141876 root=/dev/ram rw initrd=/casper/initrd.gz --\n")
        else:
            lines.append("  kernel /install/vmlinuz\n")
            lines.append("  append file=/cdrom/preseed/customiso.seed locale=en_US console-setup/ask_detect=false console-setup/layoutcode=us priority=critical ramdisk_size=141876 root=/dev/ram rw initrd=/install/initrd.gz --\n")

        f = open(isolinuxcfg, "w")
        f.writelines(lines)
        f.close()

    def generate_new_iso(self):
        self.log.info("Generating new ISO")
        oz.Guest.subprocess_check_output(["mkisofs", "-r", "-V", "Custom", "-J",
                                       "-l", "-b", "isolinux/isolinux.bin",
                                       "-c", "isolinux/boot.cat",
                                       "-no-emul-boot", "-boot-load-size", "4",
                                       "-cache-inodes", "-boot-info-table",
                                       "-v", "-v", "-o", self.output_iso,
                                       self.iso_contents])

    def generate_install_media(self, force_download=False):
        return self.iso_generate_install_media(self.url, force_download)

def get_class(tdl, config, auto):
    if tdl.update in ["6.10", "7.04"]:
        return Ubuntu610and704Guest(tdl, config, auto)
    if tdl.update in ["7.10"]:
        return UbuntuGuest(tdl, config, auto, "initrd.gz", "rtl8139", None)
    if tdl.update in ["8.04", "8.04.1", "8.04.2", "8.04.3", "8.04.4", "8.10",
                      "9.04"]:
        return UbuntuGuest(tdl, config, auto, "initrd.gz", "virtio", "virtio")
    if tdl.update in ["9.10", "10.04", "10.04.1", "10.10"]:
        return UbuntuGuest(tdl, config, auto, "initrd.lz", "virtio", "virtio")
    raise oz.OzException.OzException("Unsupported Ubuntu update " + tdl.update)
