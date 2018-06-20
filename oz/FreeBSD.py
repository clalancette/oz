# Copyright (C) 2013  harmw <harm@weites.com>
# Copyright (C) 2013-2017  Chris Lalancette <clalancette@gmail.com>

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
import oz.OzException
import oz.ozutil


class FreeBSDConfiguration(object):
    """
    Configuration class for FreeBSD.
    """
    def __init__(self, default_netdev, default_diskbus):
        self._default_netdev = default_netdev
        self._default_diskbus = default_diskbus

    @property
    def default_netdev(self):
        """
        Property method for the default netdev for this FreeBSD version.
        """
        return self._default_netdev

    @property
    def default_diskbus(self):
        """
        Property method for the default diskbus for this FreeBSD version.
        """
        return self._default_diskbus


version_to_config = {
    "11.0": FreeBSDConfiguration(default_netdev='virtio', default_diskbus='virtio'),
    "10.3": FreeBSDConfiguration(default_netdev='virtio', default_diskbus='virtio'),
    "10.2": FreeBSDConfiguration(default_netdev='virtio', default_diskbus='virtio'),
    "10.1": FreeBSDConfiguration(default_netdev='virtio', default_diskbus='virtio'),
    "10.0": FreeBSDConfiguration(default_netdev='virtio', default_diskbus='virtio'),
}


class FreeBSD(oz.Guest.CDGuest):
    """
    Class for FreeBSD 10.0, 10.1, 10.2, 10.3 and 11.0 installation.
    """
    def __init__(self, tdl, config, auto, output_disk, netdev, diskbus,
                 macaddress):
        self.config = version_to_config[tdl.update]
        if netdev is None:
            netdev = self.config.default_netdev
        if diskbus is None:
            diskbus = self.config.default_diskbus
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
            for key in keys:
                line = line.replace(key, keys[key])
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
            conf.write('autoboot_delay="0"\n')
            conf.write('vfs.root.mountfrom="cd9660:/dev/cd0"\n')
            conf.write('console="vidconsole comconsole"\n')
            conf.write('kern.panic_reboot_wait_time="-1"\n')


def get_class(tdl, config, auto, output_disk=None, netdev=None, diskbus=None,
              macaddress=None):
    """
    Factory method for FreeBSD installs.
    """
    if tdl.update in version_to_config.keys():
        return FreeBSD(tdl, config, auto, output_disk, netdev, diskbus,
                       macaddress)


def get_supported_string():
    """
    Return supported versions as a string.
    """
    return "FreeBSD: " + ", ".join(sorted(version_to_config.keys()))
