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

import re
import os
import shutil

import ozutil
import RedHat
import OzException

class RHL9Guest(RedHat.RedHatCDGuest):
    def __init__(self, tdl, config, auto):
        RedHat.RedHatCDGuest.__init__(self, tdl, "rtl8139", None, None, None,
                                      config)

        self.ks_file = auto
        if self.ks_file is None:
            self.ks_file = ozutil.generate_full_auto_path("rhl-" + self.tdl.update + "-jeos.ks")

        self.url = self.check_url(self.tdl, iso=False, url=True)

        if self.tdl.arch != "i386":
            raise OzException.OzException("Invalid arch " + self.tdl.arch + "for RHL guest")

    def modify_iso(self):
        self.log.debug("Putting the kickstart in place")

        output_ks = os.path.join(self.iso_contents, "ks.cfg")

        if self.ks_file == ozutil.generate_full_auto_path("rhl-" + self.tdl.update + "-jeos.ks"):
            def kssub(line):
                if re.match("^url", line):
                    return "url --url " + self.url + "\n"
                elif re.match("^rootpw", line):
                    return "rootpw " + self.rootpw + "\n"
                else:
                    return line

            self.copy_modify_file(self.ks_file, output_ks, kssub)
        else:
            shutil.copy(self.ks_file, output_ks)

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
        lines.append("  append initrd=initrd.img ks=cdrom:/ks.cfg method=" + self.url + "\n")

        f = open(isolinuxcfg, "w")
        f.writelines(lines)
        f.close()

class RHL70and71and72and73and8Guest(RedHat.RedHatFDGuest):
    def __init__(self, tdl, config, auto, nicmodel):
        RedHat.RedHatFDGuest.__init__(self, tdl, config, auto,
                                      "rhl-" + tdl.update + "-jeos.ks",
                                      nicmodel)

def get_class(tdl, config, auto):
    if tdl.update in ["9"]:
        return RHL9Guest(tdl, config, auto)
    if tdl.update in ["7.2", "7.3", "8"]:
        return RHL70and71and72and73and8Guest(tdl, config, auto, "rtl8139")
    # FIXME: RHL 6.2 does not work via HTTP because of a bug in the installer;
    # when parsing a URL passed in via "method", it fails to put a / at the
    # beginning of the URL.  What this means is that when the installer goes
    # to fetch the install images via "GET path/to/netstg2.img HTTP/0.9", the
    # web server then returns an error.  To do a fully automated install, we
    # need to use an ISO, NFS or FTP install method; I could not get FTP
    # to work, but I did not try that hard
    # FIXME: RHL 6.1 fails for a different reason, namely that there is no
    # netstg2.img available in the distribution I have.  Unfortunately, I have
    # not been able to find the netstg2.img, nor an ISO of 6.1 to do an
    # alternate install.  NFS may still work here.
    # FIXME: RHL 6.0 fails for yet a different reason, a kernel panic on boot
    # The panic is:
    # VFS: Cannot open root device 08:21
    # Kernel panic: VFS: Unable to mount root fs on 08:21
    if tdl.update in ["7.0", "7.1"]:
        return RHL70and71and72and73and8Guest(tdl, config, auto, "ne2k_pci")
    raise OzException.OzException("Unsupported RHL update " + tdl.update)
