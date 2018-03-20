# Copyright (C) 2010,2011  Chris Lalancette <clalance@redhat.com>
# Copyright (C) 2012-2017  Chris Lalancette <clalancette@gmail.com>

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
RHEL-3 installation
"""

import os
import re

import oz.OzException
import oz.RedHat
import oz.ozutil

versions = ["GOLD", "U1", "U2", "U3", "U4", "U5", "U6", "U7", "U8", "U9"]


class RHEL3Guest(oz.RedHat.RedHatLinuxCDGuest):
    """
    Class for RHEL-3 GOLD, U1, U2, U3, U4, U5, U6, U7, U8, and U9 installation.
    """
    def __init__(self, tdl, config, auto, output_disk, netdev, diskbus,
                 macaddress):
        iso_support = True
        if tdl.distro == "RHEL-3":
            iso_support = False

        # although we could use ext2 for the initrdtype here (and hence get
        # fast initial installs), it isn't super reliable on RHEL-3.  Just
        # disable it and fall back to the boot.iso method which is more reliable
        oz.RedHat.RedHatLinuxCDGuest.__init__(self, tdl, config, auto,
                                              output_disk, netdev, diskbus,
                                              iso_support, True, None,
                                              macaddress)

        # override the sshd_config value set in RedHatLinuxCDGuest.__init__
        self.sshd_config = """\
SyslogFacility AUTHPRIV
PasswordAuthentication yes
ChallengeResponseAuthentication no
X11Forwarding yes
Subsystem	sftp	/usr/libexec/openssh/sftp-server
"""

    def _modify_iso(self):
        """
        Method to make the boot ISO auto-boot with appropriate parameters.
        """
        self._copy_kickstart(os.path.join(self.iso_contents, "ks.cfg"))

        initrdline = "  append initrd=initrd.img ks=cdrom:/ks.cfg method="
        if self.tdl.installtype == "url":
            initrdline += self.url
        else:
            initrdline += "cdrom:/dev/cdrom"
        self._modify_isolinux(initrdline)

    def _check_pvd(self):
        """
        Method to ensure the the boot ISO for an ISO install is a DVD
        """
        cdfd = open(self.orig_iso, "r")
        pvd = self._get_primary_volume_descriptor(cdfd)
        cdfd.close()

        if pvd.system_identifier != "LINUX                           ":
            raise oz.OzException.OzException("Invalid system identifier on ISO for " + self.tdl.distro + " install")

        if self.tdl.distro == "RHEL-3":
            if self.tdl.installtype == "iso":
                raise oz.OzException.OzException("BUG: shouldn't be able to reach RHEL-3 with ISO checking")
            # The boot ISOs for RHEL-3 don't have a whole lot of identifying
            # information.  We just pass through here, doing nothing
        else:
            if self.tdl.installtype == "iso":
                centos_disk_1 = re.match(r"CentOS-3(\.[0-9])? Disk 1", pvd.volume_identifier)
                centos_server = re.match(r"CentOS-3(\.[0-9])? server", pvd.volume_identifier)
                centos_dvd = re.match(r"CentOS-3(\.[0-9])? " + self.tdl.arch + " DVD", pvd.volume_identifier)
                if not centos_disk_1 and not centos_server and not centos_dvd:
                    raise oz.OzException.OzException("Only DVDs are supported for CentOS-3 ISO installs")
            # The boot ISOs for CentOS-3 don't have a whole lot of identifying
            # information.  We just pass through here, doing nothing

    def get_auto_path(self):
        """
        Method to create the correct path to the RHEL 3 kickstart files.
        """
        return oz.ozutil.generate_full_auto_path("RHEL3.auto")


def get_class(tdl, config, auto, output_disk=None, netdev=None, diskbus=None,
              macaddress=None):
    """
    Factory method for RHEL-3 installs.
    """
    if tdl.update in versions:
        return RHEL3Guest(tdl, config, auto, output_disk, netdev, diskbus,
                          macaddress)


def get_supported_string():
    """
    Return supported versions as a string.
    """
    return "RHEL/CentOS 3: " + ", ".join(versions)
