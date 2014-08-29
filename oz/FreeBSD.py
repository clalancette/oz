# Copyright (C) 2013  harmw <harm@weites.com>
# Copyright (C) 2013  Chris Lalancette <clalancette@gmail.com>

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
FreeBSD installation
"""

import os

import oz.Guest
import oz.ozutil
import oz.OzException

class FreeBSD(oz.Guest.CDGuest):
    """
    Class for FreeBSD 10.0 installation.
    """
    def __init__(self, tdl, config, auto, output_disk, netdev, diskbus,
                 macaddress):
        oz.Guest.CDGuest.__init__(self, tdl, config, auto, output_disk,
                                  netdev, "localtime", "usb", diskbus, True,
                                  False, macaddress)

    def _generate_new_iso(self):
        """
        Method to create a new ISO based on the modified CD/DVD.
        """
        self.log.debug("Generating new ISO")
        oz.ozutil.subprocess_check_output(["genisoimage",
                                           "-R", "-no-emul-boot",
                                           "-b", "boot/cdboot", "-v",
                                           "-o", self.output_iso,
                                           self.iso_contents],
                                          printfn=self.log.debug)

    def _modify_iso(self):
        """
        Method to make the boot ISO auto-boot with appropriate parameters.
        """
        self.log.debug("Modifying ISO")

        def _replace(line):
            """
            Method that is called back from copy_modify_file to replace
            the rootpassword in the installerconfig file
            """
            keys = {
                '#ROOTPW#': self.rootpw,
            }
            for key, val in keys.iteritems():
                line = line.replace(key, val)
            return line

        # Copy the installconfig file to /etc/ on the iso image so bsdinstall(8)
        # can use that to do an unattended installation. This rules file
        # contains both setup rules and a post script. This stage also prepends
        # the post script with additional commands so it's possible to install
        # extra	packages specified in the .tdl file.

        outname = os.path.join(self.iso_contents, "etc", "installerconfig")
        oz.ozutil.copy_modify_file(self.auto, outname, _replace)

        # Make sure the iso can be mounted at boot, otherwise this error shows
        # up after booting the kernel:
        #  mountroot: waiting for device /dev/iso9660/FREEBSD_INSTALL ...
	#  Mounting from cd9660:/dev/iso9660/FREEBSD_INSTALL failed with error 19.

        loaderconf = os.path.join(self.iso_contents, "boot", "loader.conf")
        with open(loaderconf, 'w') as conf:
            conf.write('vfs.root.mountfrom="cd9660:/dev/cd0"\n')

def get_class(tdl, config, auto, output_disk=None, netdev=None, diskbus=None,
              macaddress=None):
    """
    Factory method for FreeBSD installs.
    """
    if tdl.update in ["10.0"]:
        if netdev is None:
            netdev = 'virtio'
        if diskbus is None:
            diskbus = 'virtio'
    return FreeBSD(tdl, config, auto, output_disk, netdev, diskbus,
                   macaddress)

def get_supported_string():
    """
    Return supported versions as a string.
    """
    return "FreeBSD: 10"
