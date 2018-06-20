# Copyright (C) 2011  Chris Lalancette <clalance@redhat.com>
# Copyright (C) 2012-2017  Chris Lalancette <clalancette@gmail.com>

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

import os
import re
import shutil

import oz.Guest
import oz.OzException
import oz.ozutil


class MandrivaConfiguration(object):
    """
    Configuration class for Mandriva.
    """
    def __init__(self, old_path):
        self._old_path = old_path

    @property
    def old_path(self):
        """
        Property method for whether this uses the old style paths.
        """
        return self._old_path


version_to_config = {
    "2008.0": MandrivaConfiguration(old_path=False),
    "2007.0": MandrivaConfiguration(old_path=False),
    "2006.0": MandrivaConfiguration(old_path=True),
    "2005": MandrivaConfiguration(old_path=True),
}


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

        self.config = version_to_config[tdl.update]

    def _modify_iso(self):
        """
        Method to make the boot ISO auto-boot with appropriate parameters.
        """
        self.log.debug("Modifying ISO")

        self.log.debug("Copying cfg file")

        pathdir = self.iso_contents
        if not self.config.old_path:
            pathdir = os.path.join(self.iso_contents, self.mandriva_arch)

        outname = os.path.join(pathdir, "auto_inst.cfg")

        if self.default_auto_file():

            def _cfg_sub(line):
                """
                Method that is called back from oz.ozutil.copy_modify_file() to
                modify preseed files as appropriate for Mandriva.
                """
                if re.search("'password' =>", line):
                    return "			'password' => '" + self.rootpw + "',\n"
                return line

            oz.ozutil.copy_modify_file(self.auto, outname, _cfg_sub)
        else:
            shutil.copy(self.auto, outname)

        self.log.debug("Modifying isolinux.cfg")
        isolinuxcfg = os.path.join(pathdir, "isolinux", "isolinux.cfg")
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
        if not self.config.old_path:
            isolinuxdir = self.mandriva_arch

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


def get_class(tdl, config, auto, output_disk=None, netdev=None, diskbus=None,
              macaddress=None):
    """
    Factory method for Mandriva installs.
    """
    if tdl.update in version_to_config.keys():
        return MandrivaGuest(tdl, config, auto, output_disk, netdev, diskbus,
                             macaddress)


def get_supported_string():
    """
    Return supported versions as a string.
    """
    return "Mandriva: " + ", ".join(sorted(version_to_config.keys()))
