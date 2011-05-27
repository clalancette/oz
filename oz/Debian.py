# Copyright (C) 2011  Chris Lalancette <clalance@redhat.com>

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
import os

import oz.Guest
import oz.ozutil
import oz.OzException

class DebianGuest(oz.Guest.CDGuest):
    def __init__(self, tdl, config, auto):
        oz.Guest.CDGuest.__init__(self, tdl, 'virtio', None, None, 'virtio',
                                  config)

        self.preseed_file = auto
        if self.preseed_file is None:
            self.preseed_file = oz.ozutil.generate_full_auto_path("debian-" + self.tdl.update + "-jeos.preseed")

        self.url = self.check_url(self.tdl, iso=True, url=False)

    def modify_iso(self):
        self.log.debug("Modifying ISO")

        self.log.debug("Copying preseed file")
        self.mkdir_p(os.path.join(self.iso_contents, "preseed"))
        shutil.copy(self.preseed_file, os.path.join(self.iso_contents,
                                                    "preseed",
                                                    "customiso.seed"))

        if self.tdl.arch == "x86_64":
            installdir = "/install.amd"
        else:
            # arch == i386
            installdir = "/install.386"

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
        f.write("  kernel " + installdir + "/vmlinuz\n")
        f.write("  append file=/cdrom/preseed/customiso.seed debian-installer/locale=en_US console-setup/layoutcode=us netcfg/choose_interface=auto priority=critical initrd=" + installdir + "/initrd.gz --\n")
        f.close()

    def generate_new_iso(self):
        self.log.info("Generating new ISO")
        oz.Guest.subprocess_check_output(["mkisofs", "-r", "-V", "Custom", "-J",
                                          "-l", "-b", "isolinux/isolinux.bin",
                                          "-c", "isolinux/boot.cat",
                                          "-no-emul-boot",
                                          "-boot-load-size", "4",
                                          "-cache-inodes", "-boot-info-table",
                                          "-v", "-v", "-o", self.output_iso,
                                          self.iso_contents])

    def generate_install_media(self, force_download=False):
        return self.iso_generate_install_media(self.url, force_download)

def get_class(tdl, config, auto):
    if tdl.update in ["5", "6"]:
        return DebianGuest(tdl, config, auto)
    raise oz.OzException.OzException("Unsupported Debian update " + tdl.update)
