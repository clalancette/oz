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

import shutil
import re
import os

import ozutil
import RedHat
import OzException

class FedoraCoreGuest(RedHat.RedHatCDGuest):
    def __init__(self, tdl, config, auto):
        RedHat.RedHatCDGuest.__init__(self, tdl.name, tdl.distro, tdl.update,
                                      tdl.arch, tdl.installtype, 'rtl8139',
                                      None, None, None, config)

        self.tdl = tdl
        self.ks_file = auto
        if self.ks_file is None:
            self.ks_file = ozutil.generate_full_auto_path("fedoracore-" + self.tdl.update + "-jeos.ks")

        self.url = self.check_url(self.tdl, iso=True, url=True)

        # FIXME: if doing an ISO install, we have to check that the ISO passed
        # in is the DVD, not the CD (since we can't change disks midway)

    def modify_iso(self):
        self.log.debug("Putting the kickstart in place")

        shutil.copy(self.ks_file, os.path.join(self.iso_contents, "ks.cfg"))

        self.log.debug("Modifying the boot options")
        isolinuxcfg = os.path.join(self.iso_contents, "isolinux",
                                   "isolinux.cfg")
        f = open(isolinuxcfg, "r")
        lines = f.readlines()
        f.close()
        for index, line in enumerate(lines):
            if re.match("timeout", line):
                lines[index] = "timeout 1\n"
            elif re.match("default", line):
                lines[index] = "default customiso\n"
        lines.append("label customiso\n")
        lines.append("  kernel vmlinuz\n")
        initrdline = "  append initrd=initrd.img ks=cdrom:/ks.cfg method="
        if self.tdl.installtype == "url":
            initrdline += self.url + "\n"
        else:
            initrdline += "cdrom:/dev/cdrom\n"
        lines.append(initrdline)

        f = open(isolinuxcfg, "w")
        f.writelines(lines)
        f.close()

class FedoraCore4Guest(FedoraCoreGuest):
    def generate_diskimage(self, size=10):
        self.generate_blank_diskimage()

def get_class(tdl, config, auto):
    if tdl.update in ["1", "2", "3", "5", "6"]:
        return FedoraCoreGuest(tdl, config, auto)
    if tdl.update in ["4"]:
        return FedoraCore4Guest(tdl, config, auto)
    raise OzException.OzException("Unsupported FedoraCore update " + tdl.update)
