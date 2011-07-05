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

import oz.ozutil
import oz.RedHat
import oz.OzException

class FedoraGuest(oz.RedHat.RedHatCDYumGuest):
    def __init__(self, tdl, config, auto, nicmodel, haverepo, diskbus,
                 brokenisomethod):
        oz.RedHat.RedHatCDYumGuest.__init__(self, tdl, nicmodel, diskbus,
                                            config, True, True)

        self.auto = auto

        self.haverepo = haverepo
        self.brokenisomethod = brokenisomethod

    def modify_iso(self):
        self.copy_kickstart(self.auto, "fedora-" + self.tdl.update + "-jeos.ks")

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
        self.modify_isolinux(initrdline)

    def generate_diskimage(self, size=10, force=False):
        createpart = False
        if self.tdl.update in ["11", "12"]:
            # If given a blank diskimage, Fedora 11/12 stops very early in
            # install with a message about losing all of your data on the
            # drive (it differs between them).
            #
            # To avoid that message, just create a partition table that spans
            # the entire disk
            createpart = True
        return self.internal_generate_diskimage(size, force, createpart)

def get_class(tdl, config, auto):
    if tdl.update in ["10", "11", "12", "13", "14", "15"]:
        return FedoraGuest(tdl, config, auto, "virtio", True, "virtio", True)
    if tdl.update in ["7", "8", "9"]:
        return FedoraGuest(tdl, config, auto, "rtl8139", False, None, False)
    raise oz.OzException.OzException("Unsupported Fedora update " + tdl.update)
