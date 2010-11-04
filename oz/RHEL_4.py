# Copyright (C) 2010  Chris Lalancette <clalance@redhat.com>

# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.

# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.

# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA

import Guest
import shutil
import subprocess
import re
import ozutil

class RHEL4Guest(Guest.CDGuest):
    def __init__(self, update, arch, url, ks, nicmodel, diskbus):
        Guest.CDGuest.__init__(self, "RHEL-4", update, arch, nicmodel, None, None, diskbus)
        self.ks_file = ks
        self.url = url

    def modify_iso(self):
        self.log.debug("Putting the kickstart in place")

        shutil.copy(self.ks_file, self.iso_contents + "/ks.cfg")

        self.log.debug("Modifying the boot options")
        f = open(self.iso_contents + "/isolinux/isolinux.cfg", "r")
        lines = f.readlines()
        f.close()
        for line in lines:
            if re.match("timeout", line):
                lines[lines.index(line)] = "timeout 1\n"
            elif re.match("default", line):
                lines[lines.index(line)] = "default customiso\n"
        lines.append("label customiso\n")
        lines.append("  kernel vmlinuz\n")
        lines.append("  append initrd=initrd.img ks=cdrom:/ks.cfg method=" + self.url + "\n")

        f = open(self.iso_contents + "/isolinux/isolinux.cfg", "w")
        f.writelines(lines)
        f.close()

    def generate_new_iso(self):
        self.log.debug("Generating new ISO")
        Guest.subprocess_check_output(["mkisofs", "-r", "-T", "-J", "-V",
                                       "Custom", "-b", "isolinux/isolinux.bin",
                                       "-c", "isolinux/boot.cat",
                                       "-no-emul-boot", "-boot-load-size", "4",
                                       "-boot-info-table", "-v", "-v",
                                       "-o", self.output_iso, self.iso_contents])

    def generate_install_media(self, force_download):
        self.get_original_iso(self.url + "/images/boot.iso", force_download)
        self.copy_iso()
        self.modify_iso()
        self.generate_new_iso()
        self.cleanup_iso()

def get_class(idl):
    update = idl.update()
    arch = idl.arch()

    if idl.installtype() != 'url':
        raise Exception, "RHEL-4 installs must be done via url"

    url = ozutil.check_url(idl.url())

    if update == "GOLD" or update == "U1" or update == "U2" or update == "U3" or update == "U4" or update == "U5" or update == "U6" or update == "U7":
        ks = ozutil.generate_full_auto_path("rhel-4-jeos.ks")
        return RHEL4Guest(update, arch, url, ks, "rtl8139", None)
    if update == "U8":
        ks = ozutil.generate_full_auto_path("rhel-4-virtio-jeos.ks")
        return RHEL4Guest(update, arch, url, ks, "virtio", "virtio")
    raise Exception, "Unsupported RHEL-4 update " + update
