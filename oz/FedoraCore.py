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
import os

import Guest
import ozutil
import RedHat

class FedoraCoreGuest(RedHat.RedHatCDGuest):
    def __init__(self, tdl, config, auto):
        self.tdl = tdl
        self.ks_file = auto
        if self.ks_file is None:
            self.ks_file = ozutil.generate_full_auto_path("fedoracore-" + self.tdl.update + "-jeos.ks")

        if self.tdl.installtype == 'url':
            self.url = self.tdl.url
            ozutil.deny_localhost(self.url)
        elif self.tdl.installtype == 'iso':
            self.url = self.tdl.iso
        else:
            raise Guest.OzException("FedoraCore installs must be done via url or iso")

        # FIXME: if doing an ISO install, we have to check that the ISO passed
        # in is the DVD, not the CD (since we can't change disks midway)

        RedHat.RedHatCDGuest.__init__(self, self.tdl.name, "FedoraCore",
                                      self.tdl.update, self.tdl.arch,
                                      self.tdl.installtype, 'rtl8139', None,
                                      None, None, config)

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

    def generate_install_media(self, force_download):
        self.log.info("Generating install media")
        fetchurl = self.url
        if self.tdl.installtype == 'url':
            fetchurl += "/images/boot.iso"
        self.get_original_iso(fetchurl, force_download)
        self.copy_iso()
        self.modify_iso()
        self.generate_iso()
        self.cleanup_iso()

class FedoraCore4Guest(FedoraCoreGuest):
    def generate_diskimage(self):
        self.generate_blank_diskimage()

def get_class(tdl, config, auto):
    if tdl.update in ["1", "2", "3", "5", "6"]:
        return FedoraCoreGuest(tdl, config, auto)
    if tdl.update in ["4"]:
        return FedoraCore4Guest(tdl, config, auto)
    raise Guest.OzException("Unsupported FedoraCore update " + tdl.update)
