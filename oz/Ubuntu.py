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

"""
Ubuntu installation
"""

import shutil
import re
import os

import oz.Guest
import oz.ozutil
import oz.OzException

class UbuntuGuest(oz.Guest.CDGuest):
    """
    Class for Ubuntu 6.06, 6.10, 7.04, 7.10, 8.04, 8.10, 9.04, 9.10, 10.04, and 10.10 installation.
    """
    def __init__(self, tdl, config, auto, initrd, nicmodel, diskbus):
        oz.Guest.CDGuest.__init__(self, tdl, nicmodel, None, None, diskbus,
                                  config)

        self.casper_initrd = initrd

        self.preseed_file = auto
        if self.preseed_file is None:
            self.preseed_file = oz.ozutil.generate_full_auto_path("ubuntu-" + self.tdl.update + "-jeos.preseed")

        self.url = self._check_url(self.tdl, iso=True, url=False)

    def _check_iso_tree(self):
        if self.tdl.update in ["6.06", "6.06.1", "6.06.2", "6.10", "7.04"]:
            if os.path.isdir(os.path.join(self.iso_contents, "casper")):
                raise oz.OzException.OzException("Ubuntu %s installs can only be done using the alternate or server CDs" % (self.tdl.update))

    def _modify_iso(self):
        """
        Method to make the boot ISO auto-boot with appropriate parameters.
        """
        self.log.debug("Modifying ISO")

        self.log.debug("Copying preseed file")
        outname = os.path.join(self.iso_contents, "preseed", "customiso.seed")

        if self.preseed_file == oz.ozutil.generate_full_auto_path("ubuntu-" + self.tdl.update + "-jeos.preseed"):

            def _preseed_sub(line):
                """
                Method that is called back from oz.ozutil.copy_modify_file() to
                modify preseed files as appropriate for Ubuntu.
                """
                if re.match('d-i passwd/root-password password', line):
                    return 'd-i passwd/root-password password ' + self.rootpw + '\n'
                elif re.match('d-i passwd/root-password-again password', line):
                    return 'd-i passwd/root-password-again password ' + self.rootpw + '\n'
                else:
                    return line

            oz.ozutil.copy_modify_file(self.preseed_file, outname, _preseed_sub)
        else:
            shutil.copy(self.preseed_file, outname)

        self.log.debug("Modifying isolinux.cfg")
        isolinuxcfg = os.path.join(self.iso_contents, "isolinux",
                                   "isolinux.cfg")
        f = open(isolinuxcfg, 'w')
        f.write("default customiso\n")
        f.write("timeout 1\n")
        f.write("prompt 0\n")
        f.write("label customiso\n")
        f.write("  menu label ^Customiso\n")
        f.write("  menu default\n")
        if os.path.isdir(os.path.join(self.iso_contents, "casper")):
            f.write("  kernel /casper/vmlinuz\n")
            f.write("  append file=/cdrom/preseed/customiso.seed boot=casper automatic-ubiquity noprompt keyboard-configuration/layoutcode=us initrd=/casper/" + self.casper_initrd + "\n")
        else:
            keyboard = "console-setup/layoutcode=us"
            if self.tdl.update in ["6.06", "6.06.1", "6.06.2"]:
                keyboard = "kbd-chooser/method=us"
            f.write("  kernel /install/vmlinuz\n")
            f.write("  append preseed/file=/cdrom/preseed/customiso.seed debian-installer/locale=en_US " + keyboard + " netcfg/choose_interface=auto keyboard-configuration/layoutcode=us priority=critical initrd=/install/initrd.gz --\n")
        f.close()

    def _generate_new_iso(self):
        """
        Method to create a new ISO based on the modified CD/DVD.
        """
        self.log.info("Generating new ISO")
        oz.ozutil.subprocess_check_output(["mkisofs", "-r", "-V", "Custom",
                                           "-J", "-l", "-no-emul-boot",
                                           "-b", "isolinux/isolinux.bin",
                                           "-c", "isolinux/boot.cat",
                                           "-boot-load-size", "4",
                                           "-cache-inodes", "-boot-info-table",
                                           "-v", "-v", "-o", self.output_iso,
                                           self.iso_contents])

    def generate_install_media(self, force_download=False):
        """
        Method to generate the install media for Ubuntu operating
        systems.  If force_download is False (the default), then the
        original media will only be fetched if it is not cached locally.  If
        force_download is True, then the original media will be downloaded
        regardless of whether it is cached locally.
        """
        return self._iso_generate_install_media(self.url, force_download)

    def install(self, timeout=None, force=False):
        """
        Method to run the operating system installation.
        """
        if self.tdl.update in ["6.06", "6.06.1", "6.06.2", "6.10", "7.04"]:
            if not timeout:
                timeout = 3000
        return self._do_install(timeout, force, 0)

def get_class(tdl, config, auto):
    """
    Factory method for Ubuntu installs.
    """
    if tdl.update in ["6.06", "6.06.1", "6.06.2", "6.10", "7.04", "7.10"]:
        return UbuntuGuest(tdl, config, auto, "initrd.gz", "rtl8139", None)
    if tdl.update in ["8.04", "8.04.1", "8.04.2", "8.04.3", "8.04.4", "8.10",
                      "9.04"]:
        return UbuntuGuest(tdl, config, auto, "initrd.gz", "virtio", "virtio")
    if tdl.update in ["9.10", "10.04", "10.04.1", "10.04.2", "10.04.3", "10.10",
                      "11.04"]:
        return UbuntuGuest(tdl, config, auto, "initrd.lz", "virtio", "virtio")
