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

import oz.ozutil
import oz.RedHat
import oz.OzException

class RHEL4Guest(oz.RedHat.RedHatCDGuest):
    def __init__(self, tdl, config, auto, nicmodel, diskbus):
        oz.RedHat.RedHatCDGuest.__init__(self, tdl, nicmodel, None, None,
                                         diskbus, config, True, True)

        self.ks_file = auto
        if self.ks_file is None:
            self.ks_file = oz.ozutil.generate_full_auto_path("rhel-4-jeos.ks")

    def modify_iso(self):
        self.log.debug("Putting the kickstart in place")

        outname = os.path.join(self.iso_contents, "ks.cfg")

        if self.ks_file == oz.ozutil.generate_full_auto_path("rhel-4-jeos.ks"):
            def kssub(line):
                if re.match("^rootpw", line):
                    return "rootpw " + self.rootpw + '\n'
                else:
                    return line

            self.copy_modify_file(self.ks_file, outname, kssub)
        else:
            shutil.copy(self.ks_file, outname)

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

    def check_media(self):
        pvd = self.get_primary_volume_descriptor(self.orig_iso)

        # all of the below should have "LINUX" as their system_identifier,
        # so check it here
        if pvd.system_identifier != "LINUX                           ":
            raise oz.OzException.OzException("Invalid system identifier on ISO for " + self.tdl.distro + " install")

        if self.tdl.distro == "RHEL-4":
            if self.tdl.installtype == 'iso':
                # unfortunately RHEL-4 has the same volume identifier for both
                # DVDs and CDs.  To tell them apart, we assume that if the
                # size is smaller than 1GB, this is a CD
                if not re.match("RHEL/4(-U[0-9])?", pvd.volume_identifier) or (pvd.space_size * 2048) < 1 * 1024 * 1024 * 1024:
                    raise oz.OzException.OzException("Only DVDs are supported for RHEL-4 ISO installs")
            else:
                # url installs
                if not pvd.volume_identifier.startswith("Red Hat Enterprise Linux"):
                    raise oz.OzException.OzException("Invalid boot.iso for RHEL-4 URL install")
        else:
            if self.tdl.installtype == 'iso':
                if not re.match("CentOS 4(\.[0-9])?.*DVD", pvd.volume_identifier):
                    raise oz.OzException.OzException("Only DVDs are supported for CentOS-4 ISO installs")
            else:
                # url installs
                if not re.match("CentOS *", pvd.volume_identifier):
                    raise oz.OzException.OzException("Invalid boot.iso for CentOS-4 URL install")

def get_class(tdl, config, auto):
    if tdl.update in ["GOLD", "U1", "U2", "U3", "U4", "U5", "U6", "U7"]:
        return RHEL4Guest(tdl, config, auto, "rtl8139", None)
    if tdl.update in ["U8", "U9"]:
        return RHEL4Guest(tdl, config, auto, "virtio", "virtio")
    raise oz.OzException.OzException("Unsupported " + tdl.distro + " update " + tdl.update)
