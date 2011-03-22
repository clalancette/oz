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

import Guest
import ozutil
import OzException

class DebianGuest(Guest.CDGuest):
    def __init__(self, tdl, config, auto):
        self.tdl = tdl

        if self.tdl.installtype != 'iso':
            raise OzException.OzException("Debian installs must be done via iso")

        self.preseed_file = auto
        if self.preseed_file is None:
            self.preseed_file = ozutil.generate_full_auto_path("debian-" + self.tdl.update + "-jeos.preseed")

        Guest.CDGuest.__init__(self, self.tdl.name, "Debian", self.tdl.update,
                               self.tdl.arch, 'iso', 'virtio', None, None,
                               'virtio', config)

    def modify_iso(self):
        self.log.debug("Modifying ISO")

        self.log.debug("Copying preseed file")
        self.mkdir_p(os.path.join(self.iso_contents, "preseed"))
        shutil.copy(self.preseed_file, os.path.join(self.iso_contents,
                                                    "preseed",
                                                    "customiso.seed"))

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
        f.write("  kernel /install.amd/vmlinuz\n")
        f.write("  append file=/cdrom/preseed/customiso.seed debian-installer/locale=en_US console-setup/layoutcode=us netcfg/choose_interface=auto priority=critical initrd=/install.amd/initrd.gz --\n")
        f.close()

    def generate_new_iso(self):
        self.log.info("Generating new ISO")
        Guest.subprocess_check_output(["mkisofs", "-r", "-V", "Custom", "-J",
                                       "-l", "-b", "isolinux/isolinux.bin",
                                       "-c", "isolinux/boot.cat",
                                       "-no-emul-boot", "-boot-load-size", "4",
                                       "-cache-inodes", "-boot-info-table",
                                       "-v", "-v", "-o", self.output_iso,
                                       self.iso_contents])

    def generate_install_media(self, force_download=False):
        self.log.info("Generating install media")

        if not force_download and os.access(self.modified_iso_cache, os.F_OK):
            self.log.info("Using cached modified media")
            shutil.copyfile(self.modified_iso_cache, self.output_iso)
            return

        self.get_original_iso(self.tdl.iso, force_download)
        self.copy_iso()
        try:
            self.modify_iso()
            self.generate_new_iso()
            if self.cache_modified_media:
                self.log.info("Caching modified media for future use")
                shutil.copyfile(self.output_iso, self.modified_iso_cache)
        finally:
            self.cleanup_iso()

def get_class(tdl, config, auto):
    if tdl.update == "6":
        return DebianGuest(tdl, config, auto)
    raise OzException.OzException("Unsupported Debian update " + tdl.update)
