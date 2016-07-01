# Copyright (C) 2013  harmw <harm@weites.com>
# Copyright (C) 2013-2016  Chris Lalancette <clalancette@gmail.com>

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
import shutil

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

    def _generate_new_iso(self, iso):
        """
        Method to create a new ISO based on the modified CD/DVD.
        """
        self.log.debug("Generating new ISO")
        self._last_progress_percent = -1
        def _progress_cb(done, total):
            '''
            Private function to print progress of ISO mastering.
            '''
            percent = done * 100 / total
            if percent > 100:
                percent = 100
            if percent != self._last_progress_percent:
                self._last_progress_percent = percent
                self.log.debug("%d %%", percent)
        iso.write(self.output_iso, progress_cb=_progress_cb)

    def _modify_iso(self, iso):
        """
        Method to make the boot ISO auto-boot with appropriate parameters.
        """
        self.log.debug("Modifying ISO")

        outname = os.path.join(self.icicle_tmp, "installerconfig")
        if self.default_auto_file():
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

            oz.ozutil.copy_modify_file(self.auto, outname, _replace)
        else:
            shutil.copy(self.auto, outname)

        iso.add_file(outname, "/etc/installerconfig", rr_name="installerconfig")

        # Make sure the iso can be mounted at boot, otherwise this error shows
        # up after booting the kernel:
        #  mountroot: waiting for device /dev/iso9660/FREEBSD_INSTALL ...
	#  Mounting from cd9660:/dev/iso9660/FREEBSD_INSTALL failed with error 19.

        loaderconf = os.path.join(self.icicle_tmp, "loader.conf")
        with open(loaderconf, 'w') as conf:
            conf.write('vfs.root.mountfrom="cd9660:/dev/cd0"\n')
        iso.add_file(loaderconf, "/boot/loader.conf", rr_name="loader.conf")

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
