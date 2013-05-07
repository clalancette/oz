# Copyright (C) 2010,2011  Chris Lalancette <clalance@redhat.com>
# Copyright (C) 2012,2013  Chris Lalancette <clalancette@gmail.com>

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
Windows installation
"""

import random
import re
import os
import libxml2
import shutil

import oz.Guest
import oz.ozutil
import oz.OzException

class Windows(oz.Guest.CDGuest):
    """
    Shared Windows base class.
    """
    def __init__(self, tdl, config, output_disk, netdev, diskbus, macaddress):
        oz.Guest.CDGuest.__init__(self, tdl, config, output_disk, netdev,
                                  "localtime", "usb", diskbus,
                                  True, False, macaddress)

        if self.tdl.key is None:
            raise oz.OzException.OzException("A key is required when installing Windows")

class Windows_v5(Windows):
    """
    Class for Windows versions based on kernel 5.x.
    """
    def __init__(self, tdl, config, auto, output_disk, netdev, diskbus,
                 macaddress):
        Windows.__init__(self, tdl, config, output_disk, netdev, diskbus,
                         macaddress)

        if self.tdl.update == "2000" and self.tdl.arch != "i386":
            raise oz.OzException.OzException("Windows 2000 only supports i386 architecture")

        self.siffile = auto
        if self.siffile is None:
            self.siffile = oz.ozutil.generate_full_auto_path("windows-" + self.tdl.update + "-jeos.sif")

        self.winarch = self.tdl.arch
        if self.winarch == "x86_64":
            self.winarch = "amd64"

    def _generate_new_iso(self):
        """
        Method to create a new ISO based on the modified CD/DVD.
        """
        self.log.debug("Generating new ISO")
        oz.ozutil.subprocess_check_output(["genisoimage",
                                           "-b", "cdboot/boot.bin",
                                           "-no-emul-boot", "-boot-load-seg",
                                           "1984", "-boot-load-size", "4",
                                           "-iso-level", "2", "-J", "-l", "-D",
                                           "-N", "-joliet-long",
                                           "-relaxed-filenames", "-v", "-v",
                                           "-V", "Custom",
                                           "-o", self.output_iso,
                                           self.iso_contents])

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
        if self.tdl.update == "2000":
            # If given a blank diskimage, windows 2000 stops very early in
            # install with a message:
            #
            #  Setup has determined that your computer's starupt hard disk is
            #  new or has been erased...
            #
            # To avoid that message, create a partition table that spans
            # the entire disk
            createpart = True
        return self._internal_generate_diskimage(size, force, createpart)

    def _modify_iso(self):
        """
        Method to make the boot ISO auto-boot with appropriate parameters.
        """
        self.log.debug("Modifying ISO")

        os.mkdir(os.path.join(self.iso_contents, "cdboot"))
        self._geteltorito(self.orig_iso, os.path.join(self.iso_contents,
                                                      "cdboot", "boot.bin"))

        outname = os.path.join(self.iso_contents, self.winarch, "winnt.sif")

        if self.siffile == oz.ozutil.generate_full_auto_path("windows-" + self.tdl.update + "-jeos.sif"):
            # if this is the oz default siffile, we modify certain parameters
            # to make installation succeed
            computername = "OZ" + str(random.randrange(1, 900000))

            def _sifsub(line):
                """
                Method that is called back from oz.ozutil.copy_modify_file() to
                modify sif files as appropriate for Windows 2000/XP/2003.
                """
                if re.match(" *ProductKey", line):
                    return "    ProductKey=" + self.tdl.key + "\n"
                elif re.match(" *ProductID", line):
                    return "    ProductID=" + self.tdl.key + "\n"
                elif re.match(" *ComputerName", line):
                    return "    ComputerName=" + computername + "\n"
                elif re.match(" *AdminPassword", line):
                    return "    AdminPassword=" + self.rootpw + "\n"
                else:
                    return line

            oz.ozutil.copy_modify_file(self.siffile, outname, _sifsub)
        else:
            # if the user provided their own siffile, do not override their
            # choices; the user gets to keep both pieces if something breaks
            shutil.copy(self.siffile, outname)

    def install(self, timeout=None, force=False):
        """
        Method to run the operating system installation.
        """
        internal_timeout = timeout
        if internal_timeout is None:
            internal_timeout = 3600
        return self._do_install(internal_timeout, force, 1)

class Windows_v6(Windows):
    """
    Class for Windows versions based on kernel 6.x.
    """
    def __init__(self, tdl, config, auto, output_disk, netdev, diskbus,
                 macaddress):
        Windows.__init__(self, tdl, config, output_disk, netdev, diskbus,
                         macaddress)

        self.unattendfile = auto
        if self.unattendfile is None:
            self.unattendfile = oz.ozutil.generate_full_auto_path("windows-" + self.tdl.update + "-jeos.xml")

        self.winarch = "x86"
        if self.tdl.arch == "x86_64":
            self.winarch = "amd64"

    def _generate_new_iso(self):
        """
        Method to create a new ISO based on the modified CD/DVD.
        """
        self.log.debug("Generating new ISO")
        # NOTE: Windows 2008 is very picky about which arguments to genisoimage
        # will generate a bootable CD, so modify these at your own risk
        oz.ozutil.subprocess_check_output(["genisoimage",
                                           "-b", "cdboot/boot.bin",
                                           "-no-emul-boot", "-c", "BOOT.CAT",
                                           "-iso-level", "2", "-J", "-l", "-D",
                                           "-N", "-joliet-long",
                                           "-relaxed-filenames", "-v", "-v",
                                           "-V", "Custom", "-udf",
                                           "-o", self.output_iso,
                                           self.iso_contents])

    def _modify_iso(self):
        """
        Method to make the boot ISO auto-boot with appropriate parameters.
        """
        self.log.debug("Modifying ISO")

        os.mkdir(os.path.join(self.iso_contents, "cdboot"))
        self._geteltorito(self.orig_iso, os.path.join(self.iso_contents,
                                                      "cdboot", "boot.bin"))

        outname = os.path.join(self.iso_contents, "autounattend.xml")

        if self.unattendfile == oz.ozutil.generate_full_auto_path("windows-" + self.tdl.update + "-jeos.xml"):
            # if this is the oz default unattend file, we modify certain
            # parameters to make installation succeed
            doc = libxml2.parseFile(self.unattendfile)
            xp = doc.xpathNewContext()
            xp.xpathRegisterNs("ms", "urn:schemas-microsoft-com:unattend")

            for component in xp.xpathEval('/ms:unattend/ms:settings/ms:component'):
                component.setProp('processorArchitecture', self.winarch)

            keys = xp.xpathEval('/ms:unattend/ms:settings/ms:component/ms:ProductKey')
            keys[0].setContent(self.tdl.key)

            adminpw = xp.xpathEval('/ms:unattend/ms:settings/ms:component/ms:UserAccounts/ms:AdministratorPassword/ms:Value')
            adminpw[0].setContent(self.rootpw)

            autologinpw = xp.xpathEval('/ms:unattend/ms:settings/ms:component/ms:AutoLogon/ms:Password/ms:Value')
            autologinpw[0].setContent(self.rootpw)

            doc.saveFile(outname)
        else:
            # if the user provided their own unattend file, do not override
            # their choices; the user gets to keep both pieces if something
            # breaks
            shutil.copy(self.unattendfile, outname)

    def install(self, timeout=None, force=False):
        internal_timeout = timeout
        if internal_timeout is None:
            internal_timeout = 8500
        return self._do_install(internal_timeout, force, 2)

def get_class(tdl, config, auto, output_disk=None, netdev=None, diskbus=None,
              macaddress=None):
    """
    Factory method for Windows installs.
    """
    if tdl.update in ["2000", "XP", "2003"]:
        return Windows_v5(tdl, config, auto, output_disk, netdev,
                          diskbus, macaddress)
    if tdl.update in ["2008", "7", "2012", "8"]:
        return Windows_v6(tdl, config, auto, output_disk, netdev, diskbus,
                          macaddress)

def get_supported_string():
    """
    Return supported versions as a string.
    """
    return "Windows: 2000, XP, 2003, 7, 2008, 2012, 8"
