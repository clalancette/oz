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
RHEL-6 installation
"""

import oz.ozutil
import oz.RedHat
import oz.OzException

class RHEL6Guest(oz.RedHat.RedHatCDYumGuest):
    """
    Class for RHEL-6 installation.
    """
    def __init__(self, tdl, config, auto):
        oz.RedHat.RedHatCDYumGuest.__init__(self, tdl, "virtio", "virtio",
                                            config, True, True)

        self.auto = auto

    def _modify_iso(self):
        """
        Method to modify the ISO for autoinstallation.
        """
        self._copy_kickstart(self.auto, "rhel-6-jeos.ks")

        initrdline = "  append initrd=initrd.img ks=cdrom:/ks.cfg"
        if self.tdl.installtype == "url":
            initrdline += " repo=" + self.url + "\n"
        else:
            initrdline += "\n"
        self._modify_isolinux(initrdline)

def get_class(tdl, config, auto):
    """
    Factory method for RHEL-6 installs.
    """
    if tdl.update in ["0", "1"]:
        return RHEL6Guest(tdl, config, auto)
    raise oz.OzException.OzException("Unsupported " + tdl.distro + " update " + tdl.update)
