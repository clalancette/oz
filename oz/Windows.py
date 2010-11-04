# Copyright (C) 2010  Chris Lalancette <clalance@redhat.com>

# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.

# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.

# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA

import Guest
import random
import struct
import subprocess
import re
import os
import ozutil

class Windows2000andXPand2003(Guest.CDGuest):
    def __init__(self, update, arch, url, key, siffile):
        if key is None:
            raise Exception, "A key is required when installing Windows"
        Guest.CDGuest.__init__(self, "Windows", update, arch, None, "localtime", "usb", None)
        if update == "2000" and arch != "i386":
            raise Exception, "Windows 2000 only supports i386 architecture"

        self.key = key
        self.url = url
        self.siffile = siffile

    def geteltorito(self, cdfile, outfile):
        cdfile = open(cdfile, "r")

        # the 17th sector contains the boot specification, and also contains the
        # offset of the "boot" sector
        cdfile.seek(17*2048)
        # FIXME: the final "B" here (which is the bootP sector) really should be
        # an "L", but it doesn't work when I do that
        fmt = "B5sB23s41sB"
        spec = cdfile.read(struct.calcsize(fmt))
        (boot, isoIdent, version, toritoSpec, unused, bootP) = struct.unpack(fmt, spec)
        if isoIdent != "CD001" or toritoSpec != "EL TORITO SPECIFICATION":
            raise Exception, "isoIdentification not correct"

        # OK, this looks like a CD.  Seek to the boot sector, and look for the
        # header, 0x55, and 0xaa in the first 32 bytes
        cdfile.seek(bootP*2048)
        fmt = "BBH24sHBB"
        bootdata = cdfile.read(struct.calcsize(fmt))
        (header, platform, unused, manu, unused2, five, aa) = struct.unpack(fmt, bootdata)
        if header != 1 or five != 0x55 or aa != 0xaa:
            raise Exception, "Invalid boot sector"

        # OK, everything so far has checked out.  Read the default/initial boot
        # entry
        cdfile.seek(bootP*2048+32)
        fmt = "BBHBBHLB"
        defaultentry = cdfile.read(struct.calcsize(fmt))
        (boot, media, loadsegment, systemtype, unused, scount, imgstart, unused) = struct.unpack(fmt, defaultentry)
        if boot != 0x88:
            raise Exception, "Default entry invalid"
        if media == 0 or media == 4:
            count = scount
        elif media == 1:
            # 1.2MB floppy in sectors
            count = 1200*1024/512
        elif media == 2:
            # 1.44MB floppy in sectors
            count = 1440*1024/512
        elif media == 3:
            # 2.88MB floppy in sectors
            count = 2880*1024/512

        # finally, seek to "imgstart", and read "count" sectors, which contains
        # the boot image
        cdfile.seek(imgstart*2048)
        eltoritodata = cdfile.read(count*512)
        cdfile.close()

        out = open(outfile, "w")
        out.write(eltoritodata)
        out.close()

    def generate_new_iso(self):
        self.log.debug("Generating new ISO")
        Guest.subprocess_check_output(["mkisofs", "-b", "cdboot/boot.bin",
                                       "-no-emul-boot", "-boot-load-seg",
                                       "1984", "-boot-load-size", "4",
                                       "-iso-level", "2", "-J", "-l", "-D",
                                       "-N", "-joliet-long",
                                       "-relaxed-filenames", "-v", "-v",
                                       "-V", "Custom",
                                       "-o", self.output_iso, self.iso_contents])

    def modify_iso(self):
        os.mkdir(self.iso_contents + "/cdboot")
        self.geteltorito(self.orig_iso, self.iso_contents + "/cdboot/boot.bin")

        if self.arch == "i386":
            winarch = self.arch
        elif self.arch == "x86_64":
            winarch = "amd64"
        else:
            raise Exception, "Unexpected architecture " + self.arch

        computername = "OZ" + str(random.randrange(1, 900000))

        f = open(self.siffile, "r")
        lines = f.readlines()
        f.close()

        for line in lines:
            if re.match(" *ProductKey", line):
                lines[lines.index(line)] = "    ProductKey=" + self.key + "\n"
            elif re.match(" *ProductID", line):
                lines[lines.index(line)] = "    ProductID=" + self.key + "\n"
            elif re.match(" *ComputerName", line):
                lines[lines.index(line)] = "    ComputerName=" + computername + "\n"

        f = open(self.iso_contents + "/" + winarch + "/winnt.sif", "w")
        f.writelines(lines)
        f.close()

    def generate_install_media(self, force_download):
        self.get_original_iso(self.url, force_download)
        self.copy_iso()
        self.modify_iso()
        self.generate_new_iso()
        self.cleanup_iso()

    def install(self):
        self.log.info("Running install for %s" % (self.name))
        self.generate_define_xml("cdrom")
        self.libvirt_dom.create()
        self.wait_for_install_finish(1000)
        self.generate_define_xml("hd")
        self.libvirt_dom.create()
        self.wait_for_install_finish(3600)
        self.generate_define_xml("hd", want_install_disk=False)

def get_class(idl):
    update = idl.update()
    arch = idl.arch()
    key = idl.key()
    sif = ozutil.generate_full_auto_path("windows-" + update + "-jeos.sif")

    isourl = ozutil.check_url(idl.iso())

    if idl.installtype() != 'iso':
        raise Exception, "Windows installs must be done via iso"

    if update == "2000" or update == "XP" or update == "2003":
        return Windows2000andXPand2003(update, arch, isourl, key, sif)
    raise Exception, "Unsupported Windows update " + update
