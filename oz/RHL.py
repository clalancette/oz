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

import re
import os
import shutil

import oz.ozutil
import oz.RedHat
import oz.OzException

class RHL9Guest(oz.RedHat.RedHatCDGuest):
    def __init__(self, tdl, config, auto):
        oz.RedHat.RedHatCDGuest.__init__(self, tdl, "rtl8139", None, None, None,
                                         config, False, True)

        self.auto = auto

        if self.tdl.arch != "i386":
            raise oz.OzException.OzException("Invalid arch " + self.tdl.arch + "for RHL guest")

    def modify_iso(self):
        self.log.debug("Putting the kickstart in place")

        outname = os.path.join(self.iso_contents, "ks.cfg")

        if self.auto is None:
            def kssub(line):
                # because we need to do this URL substitution here, we can't use
                # the generic "copy_kickstart()" method
                if re.match("^url", line):
                    return "url --url " + self.url + "\n"
                elif re.match("^rootpw", line):
                    return "rootpw " + self.rootpw + "\n"
                else:
                    return line

            self.copy_modify_file(oz.ozutil.generate_full_auto_path("rhl-" + self.tdl.update + "-jeos.ks"),
                                                                    outname,
                                                                    kssub)
        else:
            shutil.copy(self.auto, outname)

        initrdline = "  append initrd=initrd.img ks=cdrom:/ks.cfg method=" + self.url + "\n"
        self.modify_isolinux(initrdline)

class RHL70and71and72and73and8Guest(oz.RedHat.RedHatFDGuest):
    def __init__(self, tdl, config, auto, nicmodel):
        oz.RedHat.RedHatFDGuest.__init__(self, tdl, config, auto,
                                         "rhl-" + tdl.update + "-jeos.ks",
                                         nicmodel)

def get_class(tdl, config, auto):
    if tdl.update in ["9"]:
        return RHL9Guest(tdl, config, auto)
    if tdl.update in ["7.2", "7.3", "8"]:
        return RHL70and71and72and73and8Guest(tdl, config, auto, "rtl8139")
    if tdl.update in ["7.0", "7.1"]:
        return RHL70and71and72and73and8Guest(tdl, config, auto, "ne2k_pci")
    raise oz.OzException.OzException("Unsupported RHL update " + tdl.update)
