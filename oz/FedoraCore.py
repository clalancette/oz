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

class FedoraCoreGuest(oz.RedHat.RedHatCDGuest):
    def __init__(self, tdl, config, auto):
        oz.RedHat.RedHatCDGuest.__init__(self, tdl, 'rtl8139', None, config,
                                         True, True)

        self.auto = auto

        # FIXME: if doing an ISO install, we have to check that the ISO passed
        # in is the DVD, not the CD (since we can't change disks midway)

    def modify_iso(self):
        self.copy_kickstart(self.auto,
                            "fedoracore-" + self.tdl.update + "-jeos.ks")

        initrdline = "  append initrd=initrd.img ks=cdrom:/ks.cfg method="
        if self.tdl.installtype == "url":
            initrdline += self.url + "\n"
        else:
            initrdline += "cdrom:/dev/cdrom\n"
        self.modify_isolinux(initrdline)

def get_class(tdl, config, auto):
    if tdl.update in ["1", "2", "3", "4", "5", "6"]:
        return FedoraCoreGuest(tdl, config, auto)
    raise oz.OzException.OzException("Unsupported FedoraCore update " + tdl.update)
