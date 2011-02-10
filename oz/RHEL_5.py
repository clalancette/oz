# Copyright (C) 2010,2011  Chris Lalancette <clalance@redhat.com>

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

import shutil
import re
import struct
import os

import Guest
import ozutil
import RedHat

class RHEL5Guest(RedHat.RedHatCDYumGuest):
    def __init__(self, tdl, config, auto, nicmodel, diskbus):
        self.tdl = tdl

        self.ks_file = auto
        if self.ks_file is None:
            self.ks_file = ozutil.generate_full_auto_path("rhel-5-jeos.ks")

        if self.tdl.installtype == 'url':
            self.url = self.tdl.url
            ozutil.deny_localhost(self.url)
        elif self.tdl.installtype == 'iso':
            self.url = self.tdl.iso
        else:
            raise Guest.OzException("RHEL-5 installs must be done via url or iso")

        RedHat.RedHatCDYumGuest.__init__(self, self.tdl.name, "RHEL-5",
                                         self.tdl.update, self.tdl.arch,
                                         self.tdl.installtype, nicmodel, None,
                                         None, diskbus, config)

    def modify_iso(self):
        self.log.debug("Putting the kickstart in place")

        shutil.copy(self.ks_file, os.path.join(self.iso_contents, "ks.cfg"))

        self.log.debug("Modifying the boot options")
        isolinuxcfg = os.path.join(self.iso_contents, "isolinux", "isolinux.cfg")
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
        # we use this function to check to make sure that the ISO we downloaded
        # is the DVD ISO, not the CD one.
        cdfile = open(self.orig_iso, 'r')

        # the first 32768 bytes are unused by ISO 9660.  The 16th sector
        # contains the primary volume descriptor
        cdfile.seek(16*2048)
        fmt = "=B5sBB32s32sQLL32sHHHH"
        (desc_type, identifier, version, unused1, system_identifier, volume_identifier, unused2, space_size_le, space_size_be, unused3, set_size_le, set_size_be, seqnum_le, seqnum_be) = struct.unpack(fmt, cdfile.read(struct.calcsize(fmt)))
        cdfile.close()

        if desc_type != 0x1:
            raise Guest.OzException("Invalid primary volume descriptor")
        if identifier != "CD001":
            raise Guest.OzException("invalid CD isoIdentification")
        if unused1 != 0x0:
            raise Guest.OzException("data in unused field")
        if unused2 != 0x0:
            raise Guest.OzException("data in 2nd unused field")

        if not re.match("RHEL/5(\.[0-9])? " + self.arch + " DVD", volume_identifier):
            raise Guest.OzException("Only DVDs are supported for RHEL-5 ISO installs")

def get_class(tdl, config, auto):
    if tdl.update in ["GOLD", "U1", "U2", "U3"]:
        return RHEL5Guest(tdl, config, auto, "rtl8139", None)
    if tdl.update in ["U4", "U5", "U6"]:
        return RHEL5Guest(tdl, config, auto, "virtio", "virtio")
    raise Guest.OzException("Unsupported RHEL-5 update " + tdl.update)
