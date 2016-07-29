# Copyright (C) 2011  Chris Lalancette <clalance@redhat.com>
# Copyright (C) 2012-2016  Chris Lalancette <clalancette@gmail.com>

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
import os
import re

import oz.Guest
import oz.ozutil
import oz.OzException

class MandrivaGuest(oz.Guest.CDGuest):
    """
    Class for Mandriva 2005, 2006.0, 2007.0, and 2008.0 installation.
    """
    def __init__(self, tdl, config, auto, output_disk, netdev, diskbus,
                 macaddress):
        oz.Guest.CDGuest.__init__(self, tdl, config, auto, output_disk, netdev,
                                  None, None, diskbus, True, False, macaddress)

        self.mandriva_arch = self.tdl.arch
        if self.mandriva_arch == "i386":
            self.mandriva_arch = "i586"

    def _modify_iso(self, iso):
        """
        Method to make the boot ISO auto-boot with appropriate parameters.
        """
        self.log.debug("Modifying ISO")

        self.log.debug("Copying cfg file")

        outname = os.path.join(self.icicle_tmp, "auto_inst.cfg")

        if self.default_auto_file():

            def _cfg_sub(line):
                """
                Method that is called back from oz.ozutil.copy_modify_file() to
                modify preseed files as appropriate for Mandriva.
                """
                if re.search("'password' =>", line):
                    return "			'password' => '" + self.rootpw + "',\n"
                else:
                    return line

            oz.ozutil.copy_modify_file(self.auto, outname, _cfg_sub)
        else:
            shutil.copy(self.auto, outname)

        isodir = '/'
        if self.tdl.update in ["2007.0", "2008.0"]:
            isodir = os.path.join(isodir, self.mandriva_arch)
        isopath = os.path.join(isodir, "auto_inst.cfg")
        iso.add_file(isopath, rr_name="auto_inst.cfg", joliet_path=isopath)

        isolinuxcfg = os.path.join(self.icicle_tmp, "isolinux.cfg")
        with open(isolinuxcfg, 'w') as f:
            f.write("""\
default customiso
timeout 1
prompt 0
label customiso
  kernel alt0/vmlinuz
  append initrd=alt0/all.rdz ramdisk_size=128000 root=/dev/ram3 acpi=ht vga=788 automatic=method:cdrom kickstart=auto_inst.cfg
""")
        iso.rm_file("/isolinux/isolinux.cfg", rr_name="isolinux.cfg", joliet_path="/isolinux/isolinux.cfg")
        iso.add_file(isolinuxcfg, "/isolinux/isolinux.cfg", rr_name="isolinux.cfg", joliet_path="/isolinux/isolinux.cfg")

def get_class(tdl, config, auto, output_disk=None, netdev=None, diskbus=None,
              macaddress=None):
    """
    Factory method for Mandriva installs.
    """
    if tdl.update in ["2005", "2006.0", "2007.0", "2008.0"]:
        return MandrivaGuest(tdl, config, auto, output_disk, netdev, diskbus,
                             macaddress)

def get_supported_string():
    """
    Return supported versions as a string.
    """
    return "Mandriva: 2005, 2006.0, 2007.0, 2008.0"
