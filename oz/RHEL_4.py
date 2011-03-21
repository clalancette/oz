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

class RHEL4Guest(RedHat.RedHatCDGuest):
    def __init__(self, tdl, config, auto, nicmodel, diskbus):
        self.tdl = tdl

        self.ks_file = auto
        if self.ks_file is None:
            self.ks_file = ozutil.generate_full_auto_path("rhel-4-jeos.ks")

        self.url = self.check_url(self.tdl, iso=True, url=True)

        RedHat.RedHatCDGuest.__init__(self, self.tdl.name, self.tdl.distro,
                                      self.tdl.update, self.tdl.arch,
                                      self.tdl.installtype, nicmodel, None,
                                      None, diskbus, config)

    def modify_iso(self):
        self.log.debug("Putting the kickstart in place")

        shutil.copy(self.ks_file, os.path.join(self.iso_contents, "ks.cfg"))

        self.log.debug("Modifying the boot options")
        isolinuxcfg = os.path.join(self.iso_contents, "isolinux",
                                   "isolinux.cfg")
        f = open(isolinuxcfg, "r")
        lines = f.readlines()
        f.close()
        for line in lines:
            if re.match("timeout", line):
                lines[lines.index(line)] = "timeout 1\n"
            elif re.match("default", line):
                lines[lines.index(line)] = "default customiso\n"
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

    def check_dvd(self):
        if self.tdl.distro == "RHEL-4":
            f = open(os.path.join(self.iso_contents, ".discinfo"), 'r')
            lines = f.readlines()
            f.close()

            if not lines[1].startswith("Red Hat Enterprise Linux 4"):
                raise OzException.OzException("Invalid .discinfo file on ISO")
            if lines[2].strip() != self.arch:
                raise OzException.OzException("Invalid .discinfo architecture on ISO")
            if not lines[3].strip().startswith("1,2,3,4"):
                raise OzException.OzException("Only DVDs are supported for RHEL-4 ISO installs")
        else:
            volume_identifier = self.get_primary_volume_descriptor(self.orig_iso)

            if not re.match("CentOS 4(\.[0-9])?.*DVD", volume_identifier):
                raise OzException.OzException("Only DVDs are supported for CentOS-4 ISO installs")

def get_class(tdl, config, auto):
    if tdl.update in ["GOLD", "U1", "U2", "U3", "U4", "U5", "U6", "U7"]:
        return RHEL4Guest(tdl, config, auto, "rtl8139", None)
    if tdl.update in ["U8", "U9"]:
        return RHEL4Guest(tdl, config, auto, "virtio", "virtio")
    raise OzException.OzException("Unsupported " + tdl.distro + " update " + tdl.update)
