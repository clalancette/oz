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

import re
import shutil
import os

import Guest
import ozutil

class OpenSUSEGuest(Guest.CDGuest):
    def __init__(self, tdl, config, auto):
        self.tdl = tdl

        if self.tdl.installtype != 'iso':
            raise Guest.OzException("OpenSUSE installs must be done via ISO")

        self.autoyast = auto
        if self.autoyast is None:
            self.autoyast = ozutil.generate_full_auto_path("opensuse-" + self.tdl.update + "-jeos.xml")

        Guest.CDGuest.__init__(self, self.tdl.name, "OpenSUSE",
                               self.tdl.update, self.tdl.arch, 'iso',
                               "rtl8139", None, None, None, config)

    def modify_iso(self):
        self.log.debug("Putting the autoyast in place")
        shutil.copy(self.autoyast, os.path.join(self.iso_contents,
                                                "autoinst.xml"))

        self.log.debug("Modifying the boot options")
        isolinux_cfg = os.path.join(self.iso_contents, "boot", self.tdl.arch,
                                    "loader", "isolinux.cfg")
        f = open(isolinux_cfg, "r")
        lines = f.readlines()
        f.close()
        for line in lines:
            if re.match("timeout", line):
                lines[lines.index(line)] = "timeout 1\n"
            elif re.match("default", line):
                lines[lines.index(line)] = "default customiso\n"
        lines.append("label customiso\n")
        lines.append("  kernel linux\n")
        lines.append("  append initrd=initrd splash=silent instmode=cd autoyast=default")

        f = open(isolinux_cfg, "w")
        f.writelines(lines)
        f.close()

    def generate_new_iso(self):
        self.log.info("Generating new ISO")
        Guest.subprocess_check_output(["mkisofs", "-r", "-J", "-V", "Custom",
                                       "-l", "-b",
                                       "boot/" + self.tdl.arch + "/loader/isolinux.bin",
                                       "-c", "boot/" + self.tdl.arch + "/loader/boot.cat",
                                       "-no-emul-boot", "-boot-load-size", "4",
                                       "-boot-info-table", "-graft-points",
                                       "-iso-level", "4", "-pad",
                                       "-allow-leading-dots",
                                       "-o", self.output_iso,
                                       self.iso_contents])

    def generate_install_media(self, force_download):
        self.log.info("Generating install media")
        self.get_original_iso(self.tdl.iso, force_download)
        self.copy_iso()
        try:
            self.modify_iso()
            self.generate_new_iso()
        finally:
            self.cleanup_iso()

def get_class(tdl, config, auto):
    if tdl.update in ["11.0", "11.1", "11.2", "11.3"]:
        return OpenSUSEGuest(tdl, config, auto)

    raise Guest.OzException("Unsupported OpenSUSE update " + tdl.update)
