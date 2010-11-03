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

class FedoraCoreGuest(Guest.CDGuest):
    def __init__(self, update, arch, url, ks):
        Guest.CDGuest.__init__(self, "FedoraCore", update, arch, None, "rtl8139", None, None, None)
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

    def generate_install_media(self):
        self.get_original_iso(self.url + "/images/boot.iso")
        self.copy_iso()
        self.modify_iso()
        self.generate_new_iso()
        self.cleanup_iso()

class FedoraCore4Guest(FedoraCoreGuest):
    def __init__(self, arch, url):
        FedoraCoreGuest.__init__(self, "4", arch, url, "./fedoracore-4-jeos.ks")
    def generate_diskimage(self):
        self.generate_blank_diskimage()

def get_class(idl):
    update = idl.update()
    arch = idl.arch()
    ks = ozutil.generate_full_auto_path("fedoracore-" + update + "-jeos.ks")

    if idl.installtype() != 'url':
        raise Exception, "Fedora installs must be done via url"

    url = ozutil.check_url(idl.url())

    if update == "6" or update == "5" or update == "3" or update == "2" or update == "1":
        return FedoraCoreGuest(update, arch, url, ks)
    if update == "4":
        return FedoraCore4Guest(arch, url)
    raise Exception, "Unsupported FedoraCore update " + update
