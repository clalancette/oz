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
Fedora installation
"""

import os

import oz.ozutil
import oz.RedHat
import oz.OzException

class FedoraGuest(oz.RedHat.RedHatCDYumGuest):
    """
    Class for Fedora 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, and 17 installation.
    """
    def __init__(self, tdl, config, auto, nicmodel, haverepo,
                 diskbus, brokenisomethod, output_disk=None):
        # FIXME: For consistency most of the __init__ functions take self, tdl,
        # config, auto, output_disk (in that order).  However, in order to not
        # break imagefactory, we want to make output_disk have a default of
        # None, and we can't do that without putting output_disk at the end.
        directkernel = "cpio"
        if tdl.update in ["16", "17"]:
            directkernel = None
        oz.RedHat.RedHatCDYumGuest.__init__(self, tdl, config, output_disk,
                                            nicmodel, diskbus,
                                            "fedora-" + tdl.update + "-jeos.ks",
                                            True, True, directkernel)

        self.auto = auto

        self.haverepo = haverepo
        self.brokenisomethod = brokenisomethod

    def _modify_iso(self):
        """
        Method to modify the ISO for autoinstallation.
        """
        self._copy_kickstart(os.path.join(self.iso_contents, "ks.cfg"))

        if self.tdl.update == "17":
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

def get_class(tdl, config, auto, output_disk=None):
    """
    Factory method for Fedora installs.
    """
    if tdl.update in ["10", "11", "12", "13", "14", "15", "16", "17"]:
        return FedoraGuest(tdl, config, auto, "virtio", True, "virtio", True,
                           output_disk)
    if tdl.update in ["7", "8", "9"]:
        return FedoraGuest(tdl, config, auto, "rtl8139", False, None, False,
                           output_disk)
