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

import shutil
import re
import os
import parted

import oz.ozutil
import oz.RedHat
import oz.OzException

class FedoraGuest(oz.RedHat.RedHatCDYumGuest):
    def __init__(self, tdl, config, auto, nicmodel, haverepo, diskbus,
                 brokenisomethod):
        oz.RedHat.RedHatCDYumGuest.__init__(self, tdl, nicmodel, None, None,
                                            diskbus, config)

        self.ks_file = auto
        if self.ks_file is None:
            self.ks_file = oz.ozutil.generate_full_auto_path("fedora-" + self.tdl.update + "-jeos.ks")
        self.haverepo = haverepo
        self.brokenisomethod = brokenisomethod

        self.url = self.check_anaconda_url(self.tdl, iso=True, url=True)

    def modify_iso(self):
        self.log.debug("Putting the kickstart in place")

        outname = os.path.join(self.iso_contents, "ks.cfg")

        if self.ks_file == oz.ozutil.generate_full_auto_path("fedora-" + self.tdl.update + "-jeos.ks"):
            def kssub(line):
                if re.match("^rootpw", line):
                    return "rootpw " + self.rootpw + '\n'
                else:
                    return line

            self.copy_modify_file(self.ks_file, outname, kssub)
        else:
            shutil.copy(self.ks_file, outname)

        self.log.debug("Modifying the boot options")
        isolinuxcfg = os.path.join(self.iso_contents, "isolinux",
                                   "isolinux.cfg")
        f = open(isolinuxcfg, "r")
        lines = f.readlines()
        f.close()
        for index, line in enumerate(lines):
            if re.match("timeout", line):
                lines[index] = "timeout 1\n"
            elif re.match("default", line):
                lines[index] = "default customiso\n"
        lines.append("label customiso\n")
        lines.append("  kernel vmlinuz\n")
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
        lines.append(initrdline)

        f = open(isolinuxcfg, "w")
        f.writelines(lines)
        f.close()

    def generate_diskimage(self, size=10, force=False):
        if not force and os.access(self.jeos_cache_dir, os.F_OK) and os.access(self.jeos_filename, os.F_OK):
            # if we found a cached JEOS, we don't need to do anything here;
            # we'll copy the JEOS itself later on
            return

        self.log.info("Generating %dGB diskimage for %s" % (size,
                                                            self.tdl.name))

        f = open(self.diskimage, "w")
        f.truncate(size * 1024 * 1024 * 1024)
        f.close()

        if self.tdl.update in ["11", "12"]:
            # If given a blank diskimage, Fedora 11/12 stops very early in
            # install with a message about losing all of your data on the
            # drive (it differs between them).
            #
            # To avoid that message, just create a partition table that spans
            # the entire disk
            dev = parted.Device(self.diskimage)
            disk = parted.freshDisk(dev, 'msdos')
            constraint = parted.Constraint(device=dev)
            geom = parted.Geometry(device=dev, start=1, end=2)
            partition = parted.Partition(disk=disk,
                                         type=parted.PARTITION_NORMAL,
                                         geometry=geom)
            disk.addPartition(partition=partition, constraint=constraint)
            disk.commit()

def get_class(tdl, config, auto):
    if tdl.update in ["10", "11", "12", "13", "14", "15"]:
        return FedoraGuest(tdl, config, auto, "virtio", True, "virtio", True)
    if tdl.update in ["7", "8", "9"]:
        return FedoraGuest(tdl, config, auto, "rtl8139", False, None, False)
    raise oz.OzException.OzException("Unsupported Fedora update " + tdl.update)
