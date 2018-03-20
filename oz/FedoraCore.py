# Copyright (C) 2010,2011  Chris Lalancette <clalance@redhat.com>
# Copyright (C) 2012-2018  Chris Lalancette <clalancette@gmail.com>

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

import oz.OzException
import oz.RedHat
import oz.ozutil


class FedoraCoreConfiguration(object):
    """
    Configuration class for Fedora Core installation.
    """
    def __init__(self, initrdtype):
        self._initrdtype = initrdtype

    @property
    def initrdtype(self):
        """
        Property method for the type of initrd this version of Fedora uses
        ('cpio' or 'ext2').
        """
        return self._initrdtype


version_to_config = {
    '6': FedoraCoreConfiguration(initrdtype='cpio'),
    '5': FedoraCoreConfiguration(initrdtype='cpio'),
    '4': FedoraCoreConfiguration(initrdtype='cpio'),
    '3': FedoraCoreConfiguration(initrdtype='ext2'),
    '2': FedoraCoreConfiguration(initrdtype='ext2'),
    '1': FedoraCoreConfiguration(initrdtype='ext2'),
}


class FedoraCoreGuest(oz.RedHat.RedHatLinuxCDGuest):
    """
    Class for Fedora Core 1, 2, 3, 4, 5, and 6 installation.
    """
    def __init__(self, tdl, config, auto, output_disk, netdev, diskbus,
                 macaddress):
        self.config = version_to_config[tdl.update]
        oz.RedHat.RedHatLinuxCDGuest.__init__(self, tdl, config, auto,
                                              output_disk, netdev, diskbus,
                                              True, True, self.config.initrdtype,
                                              macaddress)

        # FIXME: if doing an ISO install, we have to check that the ISO passed
        # in is the DVD, not the CD (since we can't change disks midway)

    def _modify_iso(self):
        """
        Method to modify the ISO for autoinstallation.
        """
        self._copy_kickstart(os.path.join(self.iso_contents, "ks.cfg"))

        initrdline = "  append initrd=initrd.img ks=cdrom:/ks.cfg method="
        if self.tdl.installtype == "url":
            initrdline += self.url
        else:
            initrdline += "cdrom:/dev/cdrom"
        self._modify_isolinux(initrdline)

    def get_auto_path(self):
        """
        Method to create the correct path to the Fedora Core kickstart files.
        """
        return oz.ozutil.generate_full_auto_path("FedoraCore" + self.tdl.update + ".auto")


def get_class(tdl, config, auto, output_disk=None, netdev=None, diskbus=None,
              macaddress=None):
    """
    Factory method for Fedora Core installs.
    """
    if tdl.update in version_to_config.keys():
        return FedoraCoreGuest(tdl, config, auto, output_disk, netdev, diskbus,
                               macaddress)


def get_supported_string():
    """
    Return supported versions as a string.
    """
    return "Fedora Core: " + ", ".join(sorted(version_to_config.keys()))
