# Copyright (C) 2011,2012  Chris Lalancette <clalance@redhat.com>

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
Mandriva installation
"""

import shutil
import re
from os.path import join

import oz.Guest
from oz.ozutil import generate_full_auto_path, copy_modify_file, subprocess_check_output

class MandrivaGuest(oz.Guest.CDGuest):
    """
    Class for Mandriva 2005, 2006.0, 2007.0, and 2008.0 installation.
    """
    def __init__(self, tdl, config, auto, output_disk):
        oz.Guest.CDGuest.__init__(self, tdl, config, output_disk, None,
                                  None, None, None, True, False)

        self.auto = auto
        if self.auto is None:
            self.auto = generate_full_auto_path("mandriva-" + self.tdl.update + "-jeos.cfg")

        self.mandriva_arch = self.tdl.arch
        if self.mandriva_arch == "i386":
            self.mandriva_arch = "i586"

    def _modify_iso(self):
        """
        Method to make the boot ISO auto-boot with appropriate parameters.
        """
        self.log.debug("Modifying ISO")
        self.log.debug("Copying cfg file")

        if self.tdl.update in ["2007.0", "2008.0"]:
            pathdir = join(self.iso_contents, self.mandriva_arch)
        else:
            pathdir = self.iso_contents

        outname = join(pathdir, "auto_inst.cfg")

        if self.auto == generate_full_auto_path("mandriva-" + self.tdl.update + "-jeos.cfg"):
            def _cfg_sub(line):
                """
                Method that is called back from oz.ozutil.copy_modify_file() to
                modify preseed files as appropriate for Mandriva.
                """
                if re.search("'password' =>", line):
                    return "			'password' => '" + self.rootpw + "',\n"
                else:
                    return line

            copy_modify_file(self.auto, outname, _cfg_sub)
        else:
            shutil.copy(self.auto, outname)

        self.log.debug("Modifying isolinux.cfg")
        isolinuxcfg = join(pathdir, "isolinux", "isolinux.cfg")
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

        isolinuxdir = ""
        if self.tdl.update in ["2007.0", "2008.0"]:
            isolinuxdir = self.mandriva_arch

        isolinuxbin = join(isolinuxdir, "isolinux/isolinux.bin")
        isolinuxboot = join(isolinuxdir, "isolinux/boot.cat")

        subprocess_check_output(["genisoimage", "-r", "-V", "Custom",
                                 "-J", "-l", "-no-emul-boot",
                                 "-b", isolinuxbin,
                                 "-c", isolinuxboot,
                                 "-boot-load-size", "4",
                                 "-cache-inodes", "-boot-info-table",
                                 "-v", "-v", "-o", self.output_iso,
                                 self.iso_contents])

def get_class(tdl, config, auto, output_disk=None):
    """
    Factory method for Mandriva installs.
    """
    if tdl.update in ["2005", "2006.0", "2007.0", "2008.0"]:
        return MandrivaGuest(tdl, config, auto, output_disk)

def get_supported_string():
    """
    Return supported versions as a string.
    """
    return "Mandriva: 2005, 2006.0, 2007.0, 2008.0"
