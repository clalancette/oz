# Copyright (C) 2010,2011,2012  Chris Lalancette <clalance@redhat.com>

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
RHEL-4 installation
"""

import re
from os.path import join

import oz.RedHat
from oz.OzException import OzException

class RHEL4Guest(oz.RedHat.RedHatCDGuest):
    """
    Class for RHEL-4 GOLD, U1, U2, U3, U4, U5, U6, U7, U8, and U9 installation.
    """
    def __init__(self, tdl, config, auto, output_disk, nicmodel, diskbus):
        # we set initrdtype to None because RHEL-4 spews errors using direct
        # kernel/initrd booting.  The odd part is that it actually works, but
        # it looks ugly so for now we will just always use the boot.iso method
        oz.RedHat.RedHatCDGuest.__init__(self, tdl, config, output_disk,
                                         nicmodel, diskbus, "rhel-4-jeos.ks",
                                         True, True, None)

        self.auto = auto

    def _modify_iso(self):
        """
        Method to make the boot ISO auto-boot with appropriate parameters.
        """
        self._copy_kickstart(join(self.iso_contents, "ks.cfg"))

        initrdline = "  append initrd=initrd.img ks=cdrom:/ks.cfg method="
        if self.tdl.installtype == "url":
            initrdline += self.url + "\n"
        else:
            initrdline += "cdrom:/dev/cdrom\n"
        self._modify_isolinux(initrdline)

    def _check_pvd(self):
        """
        Method to ensure that boot ISO is a DVD (we cannot use boot CDs to
        install RHEL-4/CentOS-4 since it requires a switch during install,
        which we cannot detect).
        """
        cdfd = open(self.orig_iso, "r")
        pvd = self._get_primary_volume_descriptor(cdfd)
        cdfd.close()

        # all of the below should have "LINUX" as their system_identifier,
        # so check it here
        if pvd.system_identifier != "LINUX                           ":
            raise OzException("Invalid system identifier on ISO for " + self.tdl.distro + " install")

        if self.tdl.distro == "RHEL-4":
            if self.tdl.installtype == 'iso':
                # unfortunately RHEL-4 has the same volume identifier for both
                # DVDs and CDs.  To tell them apart, we assume that if the
                # size is smaller than 1GB, this is a CD
                if not re.match("RHEL/4(-U[0-9])?", pvd.volume_identifier) or (pvd.space_size * 2048) < 1 * 1024 * 1024 * 1024:
                    raise OzException("Only DVDs are supported for RHEL-4 ISO installs")
            else:
                # url installs
                if not pvd.volume_identifier.startswith("Red Hat Enterprise Linux"):
                    raise OzException("Invalid boot.iso for RHEL-4 URL install")
        elif self.tdl.distro == "CentOS-4":
            if self.tdl.installtype == 'iso':
                if not re.match("CentOS 4(\.[0-9])?.*DVD", pvd.volume_identifier):
                    raise OzException("Only DVDs are supported for CentOS-4 ISO installs")
            else:
                # url installs
                if not re.match("CentOS *", pvd.volume_identifier):
                    raise OzException("Invalid boot.iso for CentOS-4 URL install")

def get_class(tdl, config, auto, output_disk=None):
    """
    Factory method for RHEL-4 installs.
    """
    if tdl.update in ["GOLD", "U1", "U2", "U3", "U4", "U5", "U6", "U7"]:
        return RHEL4Guest(tdl, config, auto, output_disk, "rtl8139", None)
    if tdl.update in ["U8", "U9"]:
        return RHEL4Guest(tdl, config, auto, output_disk, "virtio", "virtio")

def get_supported_string():
    """
    Return supported versions as a string.
    """
    return "RHEL/CentOS/Scientific Linux 4: GOLD, U1, U2, U3, U4, U5, U6, U7, U8, U9"
