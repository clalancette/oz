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
Debian installation
"""

import shutil
import re
from os.path import join

import oz.Guest
from oz.ozutil import generate_full_auto_path, mkdir_p, copy_modify_file, subprocess_check_output

class DebianGuest(oz.Guest.CDGuest):
    """
    Class for Debian 5 and 6 installation.
    """
    def __init__(self, tdl, config, auto, output_disk):
        oz.Guest.CDGuest.__init__(self, tdl, config, output_disk, 'virtio',
                                  None, None, 'virtio', True, False)

        self.preseed_file = auto
        if self.preseed_file is None:
            self.preseed_file = generate_full_auto_path("debian-" + self.tdl.update + "-jeos.preseed")

    def _modify_iso(self):
        """
        Method to make the boot ISO auto-boot with appropriate parameters.
        """
        self.log.debug("Modifying ISO")

        self.log.debug("Copying preseed file")
        mkdir_p(join(self.iso_contents, "preseed"))

        outname = join(self.iso_contents, "preseed", "customiso.seed")

        if self.preseed_file == generate_full_auto_path("debian-" + self.tdl.update + "-jeos.preseed"):

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

            copy_modify_file(self.preseed_file, outname, _preseed_sub)
        else:
            shutil.copy(self.preseed_file, outname)

        if self.tdl.arch == "x86_64":
            installdir = "/install.amd"
        else:
            # arch == i386
            installdir = "/install.386"

        self.log.debug("Modifying isolinux.cfg")
        isolinuxcfg = join(self.iso_contents, "isolinux", "isolinux.cfg")
        with open(isolinuxcfg, 'w') as f:
            f.write("""\
default customiso
timeout 1
prompt 0
label customiso
  menu label ^Customiso
  menu default
  kernel %s/vmlinuz\
  append file=/cdrom/preseed/customiso.seed debian-installer/locale=en_US console-setup/layoutcode=us netcfg/choose_interface=auto priority=critical initrd=" + installdir + "/initrd.gz --
""" % installdir)

    def _generate_new_iso(self):
        """
        Method to create a new ISO based on the modified CD/DVD.
        """
        self.log.info("Generating new ISO")
        subprocess_check_output(["genisoimage", "-r", "-V", "Custom",
                                 "-J", "-l", "-no-emul-boot",
                                 "-b", "isolinux/isolinux.bin",
                                 "-c", "isolinux/boot.cat",
                                 "-boot-load-size", "4",
                                 "-cache-inodes", "-boot-info-table",
                                 "-v", "-v", "-o", self.output_iso,
                                 self.iso_contents])

def get_class(tdl, config, auto, output_disk=None):
    """
    Factory method for Debian installs.
    """
    if tdl.update in ["5", "6"]:
        return DebianGuest(tdl, config, auto, output_disk)

def get_supported_string():
    """
    Return supported versions as a string.
    """
    return "Debian: 5, 6"
