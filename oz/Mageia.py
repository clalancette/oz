# Copyright (C) 2013-2016  Chris Lalancette <clalancette@gmail.com>

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
Mageia installation
"""

import shutil
import os
import re

import oz.Guest
import oz.ozutil
import oz.OzException

class MageiaGuest(oz.Guest.CDGuest):
    """
    Class for Mageia 3, 4, 4.1, and 5 installation.
    """
    def __init__(self, tdl, config, auto, output_disk, netdev, diskbus,
                 macaddress):
        oz.Guest.CDGuest.__init__(self, tdl, config, auto, output_disk, netdev,
                                  None, None, diskbus, True, False, macaddress)

        self.mageia_arch = self.tdl.arch
        if self.mageia_arch == "i386":
            self.mageia_arch = "i586"

    def _modify_iso(self):
        """
        Method to make the boot ISO auto-boot with appropriate parameters.
        """
        self.log.debug("Modifying ISO")

        self.log.debug("Copying cfg file to floppy image")

        outname = os.path.join(self.iso_contents, "auto_inst.cfg")

        if self.default_auto_file():

            def _cfg_sub(line):
                """
                Method that is called back from oz.ozutil.copy_modify_file() to
                modify preseed files as appropriate for Mageia.
                """
                if re.search("'password' =>", line):
                    return "			'password' => '" + self.rootpw + "',\n"
                else:
                    return line

            oz.ozutil.copy_modify_file(self.auto, outname, _cfg_sub)
        else:
            shutil.copy(self.auto, outname)

        oz.ozutil.subprocess_check_output(["/sbin/mkfs.msdos", "-C",
                                           self.output_floppy, "1440"])
        oz.ozutil.subprocess_check_output(["mcopy", "-n", "-o", "-i",
                                           self.output_floppy, outname,
                                           "::AUTO_INST.CFG"])

        self.log.debug("Modifying isolinux.cfg")
        if self.tdl.update in ["3"]:
            isolinuxcfg = os.path.join(self.iso_contents, self.mageia_arch, "isolinux", "isolinux.cfg")
        else:
            isolinuxcfg = os.path.join(self.iso_contents, "isolinux", "isolinux.cfg")

        if self.tdl.update in ["3", "4"]:
            with open(isolinuxcfg, 'w') as f:
                f.write("""\
default customiso
timeout 1
prompt 0
label customiso
  kernel alt0/vmlinuz
  append initrd=alt0/all.rdz ramdisk_size=128000 root=/dev/ram3 acpi=ht vga=788 automatic=method:cdrom kickstart=floppy
""")
        elif self.tdl.update in ["4.1", "5"]:
            with open(isolinuxcfg, 'w') as f:
                f.write("""\
default customiso
timeout 1
prompt 0
label customiso
  kernel %s/vmlinuz
  append initrd=%s/all.rdz automatic=method:cdrom kickstart=floppy
""" % (self.mageia_arch, self.mageia_arch))

    def _generate_new_iso(self):
        """
        Method to create a new ISO based on the modified CD/DVD.
        """
        self.log.info("Generating new ISO")

        isolinuxdir = ""
        if self.tdl.update in ["3", "4"]:
            isolinuxdir = self.mageia_arch
        elif self.tdl.update in ["4.1", "5"]:
            isolinuxdir = ""

        isolinuxbin = os.path.join(isolinuxdir, "isolinux/isolinux.bin")
        isolinuxboot = os.path.join(isolinuxdir, "isolinux/boot.cat")

        oz.ozutil.subprocess_check_output(["genisoimage", "-r", "-V", "Custom",
                                           "-J", "-l", "-no-emul-boot",
                                           "-b", isolinuxbin,
                                           "-c", isolinuxboot,
                                           "-boot-load-size", "4",
                                           "-cache-inodes", "-boot-info-table",
                                           "-v", "-o", self.output_iso,
                                           self.iso_contents],
                                          printfn=self.log.debug)

    def install(self, timeout=None, force=False):
        fddev = self._InstallDev("floppy", self.output_floppy, "fda")
        return self._do_install(timeout, force, 0, None, None, None,
                                [fddev])

def get_class(tdl, config, auto, output_disk=None, netdev=None, diskbus=None,
              macaddress=None):
    """
    Factory method for Mageia installs.
    """
    if tdl.update in ["3", "4", "4.1", "5"]:
        if netdev is None:
            netdev = 'virtio'
        if diskbus is None:
            diskbus = 'virtio'
        return MageiaGuest(tdl, config, auto, output_disk, netdev, diskbus,
                           macaddress)

def get_supported_string():
    """
    Return supported versions as a string.
    """
    return "Mageia: 3, 4, 4.1, 5"
