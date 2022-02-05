# Copyright (C) 2013-2017  Chris Lalancette <clalancette@gmail.com>
# Copyright (C) 2013       Ian McLeod <imcleod@redhat.com>

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
RHEL-9 installation
"""

import os

import oz.OzException
import oz.RHEL_8
import oz.ozutil


class RHEL9Guest(oz.RHEL_8.RHEL8Guest):
    """
    Class for RHEL-9 installation
    """
    def __init__(self, tdl, config, auto, output_disk=None, netdev=None,
                 diskbus=None, macaddress=None):
        # dnf distro
        oz.RHEL_8.RHEL8Guest.__init__(self, tdl, config, auto,
                                      output_disk, netdev, diskbus,
                                       macaddress)

        # method and ks options were dropped
        self.cmdline = "inst.repo=" + self.url + " inst.ks=file:/ks.cfg"
        if self.tdl.kernel_param:
            self.cmdline += " " + self.tdl.kernel_param

        self.virtio_channel_name = 'org.fedoraproject.anaconda.log.0'

    def get_auto_path(self):
        """
        Method to create the correct path to the RHEL 9 kickstart file.
        """
        return oz.ozutil.generate_full_auto_path("RHEL9.auto")


def get_class(tdl, config, auto, output_disk=None, netdev=None, diskbus=None,
              macaddress=None):
    """
    Factory method for RHEL-9 installs.
    """
    if tdl.update.isdigit():
        if netdev is None:
            netdev = 'virtio'
        if diskbus is None:
            diskbus = 'virtio'
        return RHEL9Guest(tdl, config, auto, output_disk, netdev, diskbus,
                          macaddress)


def get_supported_string():
    """
    Return supported versions as a string.
    """
    return "RHEL 9"
