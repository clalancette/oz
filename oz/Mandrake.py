# Copyright (C) 2011  Chris Lalancette <clalance@redhat.com>
# Copyright (C) 2012,2013  Chris Lalancette <clalancette@gmail.com>

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
Mandrake installation
"""

import shutil
import os
import re

import oz.Guest
import oz.ozutil
import oz.OzException

class MandrakeGuest(oz.Guest.CDGuest):
    """
    Class for Mandrake 9.1, 9.2, 10.0, and 10.1 installation.
    """
    def __init__(self, tdl, config, auto, output_disk, netdev, diskbus,
                 macaddress):
        oz.Guest.CDGuest.__init__(self, tdl, config, auto, output_disk, netdev,
                                  None, None, diskbus, True, False, macaddress)

        if self.tdl.arch != "i386":
            raise oz.OzException.OzException("Mandrake only supports i386 architecture")

    def _modify_iso(self):
        """
        Method to make the boot ISO auto-boot with appropriate parameters.
        """
        self.log.debug("Modifying ISO")

        self.log.debug("Copying cfg file")

        outname = os.path.join(self.iso_contents, "auto_inst.cfg")

        if self.default_auto_file():

            def _cfg_sub(line):
                """
                Method that is called back from oz.ozutil.copy_modify_file() to
                modify preseed files as appropriate for Mandrake.
                """
                if re.search("'password' =>", line):
                    return "			'password' => '" + self.rootpw + "',\n"
                else:
                    return line

            oz.ozutil.copy_modify_file(self.auto, outname, _cfg_sub)
        else:
            shutil.copy(self.auto, outname)

        self.log.debug("Modifying isolinux.cfg")
        isolinuxcfg = os.path.join(self.iso_contents, "isolinux",
                                   "isolinux.cfg")
        with open(isolinuxcfg, 'w') as f:
            f.write("""\
default customiso
timeout 1
prompt 0
label customiso
  kernel alt0/vmlinuz
  append initrd=alt0/all.rdz ramdisk_size=128000 root=/dev/ram3 acpi=ht vga=788 automatic=method:cdrom kickstart=auto_inst.cfg
""")

    def _generate_new_iso(self):
        """
        Method to create a new ISO based on the modified CD/DVD.
        """
        self.log.info("Generating new ISO")
        oz.ozutil.subprocess_check_output(["genisoimage", "-r", "-V", "Custom",
                                           "-J", "-l", "-no-emul-boot",
                                           "-b", "isolinux/isolinux.bin",
                                           "-c", "isolinux/boot.cat",
                                           "-boot-load-size", "4",
                                           "-cache-inodes", "-boot-info-table",
                                           "-v", "-o", self.output_iso,
                                           self.iso_contents],
                                          printfn=self.log.debug)

class Mandrake82Guest(oz.Guest.CDGuest):
    """
    Class for Mandrake 8.2 installation.
    """
    def __init__(self, tdl, config, auto, output_disk, netdev, diskbus,
                 macaddress):
        oz.Guest.CDGuest.__init__(self, tdl, config, auto, output_disk, netdev,
                                  None, None, diskbus, True, False, macaddress)

        if self.tdl.arch != "i386":
            raise oz.OzException.OzException("Mandrake only supports i386 architecture")

    def _modify_iso(self):
        """
        Method to make the boot ISO auto-boot with appropriate parameters.
        """
        self.log.debug("Modifying ISO")

        outname = os.path.join(self.iso_contents, "auto_inst.cfg")
        if self.default_auto_file():

            def _cfg_sub(line):
                """
                Method that is called back from oz.ozutil.copy_modify_file() to
                modify preseed files as appropriate for Mandrake.
                """
                if re.search("'password' =>", line):
                    return "			'password' => '" + self.rootpw + "',\n"
                else:
                    return line

            oz.ozutil.copy_modify_file(self.auto, outname, _cfg_sub)
        else:
            shutil.copy(self.auto, outname)

        syslinux = os.path.join(self.icicle_tmp, 'syslinux.cfg')
        with open(syslinux, 'w') as f:
            f.write("""\
default customiso
timeout 1
prompt 0
label customiso
  kernel vmlinuz
  append initrd=cdrom.rdz ramdisk_size=32000 root=/dev/ram3 automatic=method:cdrom vga=788 auto_install=auto_inst.cfg
""")
        cdromimg = os.path.join(self.iso_contents, "Boot", "cdrom.img")
        oz.ozutil.subprocess_check_output(["mcopy", "-n", "-o", "-i",
                                           cdromimg, syslinux,
                                           "::SYSLINUX.CFG"],
                                          printfn=self.log.debug)

    def _generate_new_iso(self):
        """
        Method to create a new ISO based on the modified CD/DVD.
        """
        self.log.info("Generating new ISO")
        oz.ozutil.subprocess_check_output(["genisoimage", "-r", "-V", "Custom",
                                           "-J", "-cache-inodes",
                                           "-b", "Boot/cdrom.img",
                                           "-c", "Boot/boot.cat",
                                           "-v", "-o", self.output_iso,
                                           self.iso_contents],
                                          printfn=self.log.debug)

    def install(self, timeout=None, force=False):
        internal_timeout = timeout
        if internal_timeout is None:
            internal_timeout = 2500
        return self._do_install(internal_timeout, force, 0)

def get_class(tdl, config, auto, output_disk=None, netdev=None, diskbus=None,
              macaddress=None):
    """
    Factory method for Mandrake installs.
    """
    if tdl.update in ["8.2"]:
        return Mandrake82Guest(tdl, config, auto, output_disk, netdev, diskbus,
                               macaddress)
    if tdl.update in ["9.1", "9.2", "10.0", "10.1"]:
        return MandrakeGuest(tdl, config, auto, output_disk, netdev, diskbus,
                             macaddress)

def get_supported_string():
    """
    Return supported versions as a string.
    """
    return "Mandrake: 8.2, 9.1, 9.2, 10.0, 10.1"
