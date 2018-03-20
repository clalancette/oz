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
RHEL-5 installation
"""

import os
import re

import oz.OzException
import oz.RedHat
import oz.ozutil


class RHEL5Configuration(object):
    """
    Configuration class for RHEL-5 installation.
    """
    def __init__(self, default_netdev, default_diskbus):
        self._default_netdev = default_netdev
        self._default_diskbus = default_diskbus

    @property
    def default_netdev(self):
        """
        Property method for the default netdev for this version of RHEL-5.
        """
        return self._default_netdev

    @property
    def default_diskbus(self):
        """
        Property method for the default diskbus for this version of RHEL-5.
        """
        return self._default_diskbus


version_to_config = {
    "U11": RHEL5Configuration(default_netdev='virtio', default_diskbus='virtio'),
    "U10": RHEL5Configuration(default_netdev='virtio', default_diskbus='virtio'),
    "U9": RHEL5Configuration(default_netdev='virtio', default_diskbus='virtio'),
    "U8": RHEL5Configuration(default_netdev='virtio', default_diskbus='virtio'),
    "U7": RHEL5Configuration(default_netdev='virtio', default_diskbus='virtio'),
    "U6": RHEL5Configuration(default_netdev='virtio', default_diskbus='virtio'),
    "U5": RHEL5Configuration(default_netdev='virtio', default_diskbus='virtio'),
    "U4": RHEL5Configuration(default_netdev='virtio', default_diskbus='virtio'),
    "U3": RHEL5Configuration(default_netdev=None, default_diskbus=None),
    "U2": RHEL5Configuration(default_netdev=None, default_diskbus=None),
    "U1": RHEL5Configuration(default_netdev=None, default_diskbus=None),
    "GOLD": RHEL5Configuration(default_netdev=None, default_diskbus=None),
}


class RHEL5Guest(oz.RedHat.RedHatLinuxCDYumGuest):
    """
    Class for RHEL-5 GOLD, U1, U2, U3, U4, U5, U6, U7, U8, U9, U10 and U11 installation.
    """
    def __init__(self, tdl, config, auto, nicmodel, diskbus, output_disk=None,
                 macaddress=None):
        self.config = version_to_config[tdl.update]
        if nicmodel is None:
            nicmodel = self.config.default_netdev
        if diskbus is None:
            diskbus = self.config.default_diskbus
        oz.RedHat.RedHatLinuxCDYumGuest.__init__(self, tdl, config, auto,
                                                 output_disk, nicmodel, diskbus,
                                                 True, True, "cpio", macaddress,
                                                 True)

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
        Method to ensure that boot ISO is a DVD (we cannot use boot CDs to
        install RHEL-5/CentOS-5 since it requires a switch during install,
        which we cannot detect).
        """
        with open(self.orig_iso, "r") as cdfd:
            pvd = self._get_primary_volume_descriptor(cdfd)

        # all of the below should have "LINUX" as their system_identifier,
        # so check it here
        if pvd.system_identifier != "LINUX                           ":
            raise oz.OzException.OzException("Invalid system identifier on ISO for " + self.tdl.distro + " install")

        if self.tdl.distro == "RHEL-5":
            if self.tdl.installtype == 'iso':
                if not re.match(r"RHEL/5(\.[0-9]{1,2})? " + self.tdl.arch + " DVD",
                                pvd.volume_identifier):
                    raise oz.OzException.OzException("Only DVDs are supported for RHEL-5 ISO installs")
            else:
                # url installs
                if not pvd.volume_identifier.startswith("Red Hat Enterprise Linux"):
                    raise oz.OzException.OzException("Invalid boot.iso for RHEL-5 URL install")
        elif self.tdl.distro == "CentOS-5":
            # CentOS-5
            if self.tdl.installtype == 'iso':
                # unfortunately CentOS-5 has the same volume identifier for both
                # DVDs and CDs.  To tell them apart, we assume that if the
                # size is smaller than 1GB, this is a CD
                if not re.match(r"CentOS_5.[0-9]{1,2}_Final", pvd.volume_identifier) or (pvd.space_size * 2048) < 1 * 1024 * 1024 * 1024:
                    raise oz.OzException.OzException("Only DVDs are supported for CentOS-5 ISO installs")
            else:
                # url installs
                if not re.match(r"CentOS *", pvd.volume_identifier):
                    raise oz.OzException.OzException("Invalid boot.iso for CentOS-5 URL install")
        elif self.tdl.distro == "SLC-5":
            # SLC-5
            if self.tdl.installtype == 'iso':
                if not re.match(r"Scientific Linux CERN 5.[0-9]{1,2}", pvd.volume_identifier):
                    raise oz.OzException.OzException("Only DVDs are supported for SLC-5 ISO installs")
            else:
                # url installs
                if not re.match(r"CentOS *", pvd.volume_identifier):
                    raise oz.OzException.OzException("Invalid boot.iso for SLC-5 URL install")

    def get_auto_path(self):
        """
        Method to create the correct path to the RHEL 5 kickstart file.
        """
        return oz.ozutil.generate_full_auto_path("RHEL5.auto")


def get_class(tdl, config, auto, output_disk=None, netdev=None, diskbus=None,
              macaddress=None):
    """
    Factory method for RHEL-5 installs.
    """
    if tdl.update in version_to_config.keys():
        return RHEL5Guest(tdl, config, auto, netdev, diskbus, output_disk,
                          macaddress)


def get_supported_string():
    """
    Return supported versions as a string.
    """
    return "RHEL/OL/CentOS/Scientific Linux{,CERN} 5: " + ", ".join(sorted(version_to_config.keys()))
