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

"""
Fedora Core installation
"""

import os

import oz.ozutil
import oz.RedHat
import oz.OzException

class FedoraCoreGuest(oz.RedHat.RedHatCDGuest):
    """
    Class for Fedora Core 1, 2, 3, 4, 5, and 6 installation.
    """
    def __init__(self, tdl, config, auto):
        initrdtype = "cpio"
        if tdl.update in ["1", "2", "3"]:
            initrdtype = "ext2"
        oz.RedHat.RedHatCDGuest.__init__(self, tdl, 'rtl8139', None, config,
                                         "fedoracore-" + tdl.update + "-jeos.ks",
                                         True, True, initrdtype)

        self.auto = auto

        # FIXME: if doing an ISO install, we have to check that the ISO passed
        # in is the DVD, not the CD (since we can't change disks midway)

    def _modify_iso(self):
        """
        Method to modify the ISO for autoinstallation.
        """
        self._copy_kickstart(os.path.join(self.iso_contents, "ks.cfg"))

        initrdline = "  append initrd=initrd.img ks=cdrom:/ks.cfg method="
        if self.tdl.installtype == "url":
            initrdline += self.url + "\n"
        else:
            initrdline += "cdrom:/dev/cdrom\n"
        self._modify_isolinux(initrdline)

def get_class(tdl, config, auto):
    """
    Factory method for Fedora Core installs.
    """
    if tdl.update in ["1", "2", "3", "4", "5", "6"]:
        return FedoraCoreGuest(tdl, config, auto)
