# Copyright (C) 2011  Chris Lalancette <clalance@redhat.com>
# Copyright (C) 2012-2014  Chris Lalancette <clalancette@gmail.com>

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
Debian installation
"""

import shutil
import os
import re

import oz.Guest
import oz.ozutil
import oz.OzException

class DebianGuest(oz.Guest.CDGuest):
    """
    Class for Debian 5, 6 and 7 installation.
    """
    def __init__(self, tdl, config, auto, output_disk, netdev, diskbus,
                 macaddress):
        oz.Guest.CDGuest.__init__(self, tdl, config, auto, output_disk,
                                  netdev, None, None, diskbus, True, False,
                                  macaddress)

    def _modify_iso(self):
        """
        Method to make the boot ISO auto-boot with appropriate parameters.
        """
        self.log.debug("Modifying ISO")

        self.log.debug("Copying preseed file")
        oz.ozutil.mkdir_p(os.path.join(self.iso_contents, "preseed"))

        outname = os.path.join(self.iso_contents, "preseed", "customiso.seed")

        if self.default_auto_file():
            def _preseed_sub(line):
                """
                Method that is called back from oz.ozutil.copy_modify_file() to
                modify preseed files as appropriate for Debian.
                """
                if re.match('d-i passwd/root-password password', line):
                    return 'd-i passwd/root-password password ' + self.rootpw + '\n'
                elif re.match('d-i passwd/root-password-again password', line):
                    return 'd-i passwd/root-password-again password ' + self.rootpw + '\n'
                else:
                    return line

            oz.ozutil.copy_modify_file(self.auto, outname, _preseed_sub)
        else:
            shutil.copy(self.auto, outname)

        # arch == i386
        installdir = "/install.386"
        if self.tdl.arch == "x86_64":
            installdir = "/install.amd"

        self.log.debug("Modifying isolinux.cfg")
        isolinuxcfg = os.path.join(self.iso_contents, "isolinux", "isolinux.cfg")
        extra = ""
        if self.tdl.update in ["7"]:
            extra = "auto=true "

        with open(isolinuxcfg, 'w') as f:
            f.write("""\
default customiso
timeout 1
prompt 0
label customiso
  menu label ^Customiso
  menu default
  kernel %s/vmlinuz
  append file=/cdrom/preseed/customiso.seed %sdebian-installer/locale=en_US console-setup/layoutcode=us netcfg/choose_interface=auto priority=critical initrd=%s/initrd.gz --
""" % (installdir, extra, installdir))

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

def get_class(tdl, config, auto, output_disk=None, netdev=None, diskbus=None,
              macaddress=None):
    """
    Factory method for Debian installs.
    """
    if tdl.update in ["5", "6", "7"]:
        if netdev is None:
            netdev = 'virtio'
        if diskbus is None:
            diskbus = 'virtio'
        return DebianGuest(tdl, config, auto, output_disk, netdev, diskbus,
                           macaddress)

def get_supported_string():
    """
    Return supported versions as a string.
    """
    return "Debian: 5, 6, 7"
