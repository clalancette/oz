# Copyright (C) 2010,2011  Chris Lalancette <clalance@redhat.com>
# Copyright (C) 2012-2014  Chris Lalancette <clalancette@gmail.com>

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
Fedora installation
"""

import os

import oz.ozutil
import oz.RedHat
import oz.OzException

class FedoraGuest(oz.RedHat.RedHatLinuxCDYumGuest):
    """
    Class for Fedora 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, and 21 installation.
    """
    def __init__(self, tdl, config, auto, nicmodel, haverepo, diskbus,
                 brokenisomethod, output_disk=None, macaddress=None,
                 assumed_update=None):
        directkernel = "cpio"
        if tdl.update in ["16", "17"]:
            directkernel = None
        self.assumed_update = assumed_update

        oz.RedHat.RedHatLinuxCDYumGuest.__init__(self, tdl, config, auto,
                                                 output_disk, nicmodel, diskbus,
                                                 True, True, directkernel,
                                                 macaddress)

        if self.assumed_update is not None:
            self.log.warning("==== WARN: TDL contains Fedora update %s, which is newer than Oz knows about; pretending this is Fedora %s, but this may fail ====", tdl.update, assumed_update)

        self.haverepo = haverepo
        self.brokenisomethod = brokenisomethod

    def _modify_iso(self):
        """
        Method to modify the ISO for autoinstallation.
        """
        self._copy_kickstart(os.path.join(self.iso_contents, "ks.cfg"))

        if self.tdl.update in ["17", "18", "19", "20", "21"]:
            initrdline = "  append initrd=initrd.img ks=cdrom:/dev/cdrom:/ks.cfg"
        else:
            initrdline = "  append initrd=initrd.img ks=cdrom:/ks.cfg"
        if self.tdl.installtype == "url":
            if self.haverepo:
                initrdline += " repo="
            else:
                initrdline += " method="
            initrdline += self.url + "\n"
        else:
            # if the installtype is iso, then due to a bug in anaconda we leave
            # out the method completely
            if not self.brokenisomethod:
                initrdline += " method=cdrom:/dev/cdrom"
            initrdline += "\n"
        self._modify_isolinux(initrdline)

    def generate_diskimage(self, size=10, force=False):
        """
        Method to generate a diskimage.  By default, a blank diskimage of
        10GB will be created; the caller can override this with the size
        parameter, specified in GB.  If force is False (the default), then
        a diskimage will not be created if a cached JEOS is found.  If
        force is True, a diskimage will be created regardless of whether a
        cached JEOS exists.  See the oz-install man page for more
        information about JEOS caching.
        """
        createpart = False
        if self.tdl.update in ["11", "12"]:
            # If given a blank diskimage, Fedora 11/12 stops very early in
            # install with a message about losing all of your data on the
            # drive (it differs between them).
            #
            # To avoid that message, just create a partition table that spans
            # the entire disk
            createpart = True
        return self._internal_generate_diskimage(size, force, createpart)

    def get_auto_path(self):
        """
        Method to create the correct path to the Fedora kickstart files.
        """
        # If we are doing our best with an unknown Fedora update, use the
        # newest known auto file; otherwise, do the usual thing.
        if self.assumed_update is not None:
            return oz.ozutil.generate_full_auto_path(self.tdl.distro + self.assumed_update + ".auto")
        else:
            return oz.ozutil.generate_full_auto_path(self.tdl.distro + self.tdl.update + ".auto")

def get_class(tdl, config, auto, output_disk=None, netdev=None, diskbus=None,
              macaddress=None):
    """
    Factory method for Fedora installs.
    """
    newer_distros = ["18", "19", "20", "21"]

    if int(tdl.update) > int(newer_distros[-1]):
        if netdev is None:
            netdev = 'virtio'
        if diskbus is None:
            diskbus = 'virtio'
        return FedoraGuest(tdl, config, auto, netdev, True, diskbus, False,
                           output_disk, macaddress, newer_distros[-1])

    if tdl.update in newer_distros:
        if netdev is None:
            netdev = 'virtio'
        if diskbus is None:
            diskbus = 'virtio'
        return FedoraGuest(tdl, config, auto, netdev, True, diskbus, False,
                           output_disk, macaddress, None)

    if tdl.update in ["10", "11", "12", "13", "14", "15", "16", "17"]:
        if netdev is None:
            netdev = 'virtio'
        if diskbus is None:
            diskbus = 'virtio'
        return FedoraGuest(tdl, config, auto, netdev, True, diskbus, True,
                           output_disk, macaddress, None)

    if tdl.update in ["7", "8", "9"]:
        return FedoraGuest(tdl, config, auto, netdev, False, diskbus, False,
                           output_disk, macaddress, None)

def get_supported_string():
    """
    Return supported versions as a string.
    """
    return "Fedora: 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21"
