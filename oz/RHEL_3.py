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

class RHEL3Guest(RedHat.RedHatCDGuest):
    def __init__(self, tdl, config, auto):
        RedHat.RedHatCDGuest.__init__(self, tdl, None, None, None, None, config)

        self.ks_file = auto
        if self.ks_file is None:
            self.ks_file = ozutil.generate_full_auto_path("rhel-3-jeos.ks")

        iso_support = True
        if self.tdl.distro == "RHEL-3":
            iso_support = False

        self.url = self.check_url(self.tdl, iso=iso_support, url=True)

        # override the sshd_config value set in RedHatCDGuest.__init__
        self.sshd_config = \
"""SyslogFacility AUTHPRIV
PasswordAuthentication yes
ChallengeResponseAuthentication no
X11Forwarding yes
Subsystem	sftp	/usr/libexec/openssh/sftp-server
"""

    def modify_iso(self):
        self.log.debug("Putting the kickstart in place")

        outname = os.path.join(self.iso_contents, "ks.cfg")

        if self.ks_file == ozutil.generate_full_auto_path("rhel-3-jeos.ks"):
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
        if self.tdl.installtype != 'iso':
            return

        # RHEL-3 can't possibly reach here, since we only allow URL installs
        # there.  Therefore this is only to check CentOS-3 DVDs
        pvd = self.get_primary_volume_descriptor(self.orig_iso)
        if not re.match("CentOS-3(\.[0-9])? " + self.tdl.arch + " DVD$",
                        pvd.volume_identifier):
            raise OzException.OzException("Only DVDs are supported for CentOS-3 ISO installs")

def get_class(tdl, config, auto):
    if tdl.update in ["GOLD", "U1", "U2", "U3", "U4", "U5", "U6", "U7", "U8", "U9"]:
        return RHEL3Guest(tdl, config, auto)
    raise OzException.OzException("Unsupported " + tdl.distro + " update " + tdl.update)
