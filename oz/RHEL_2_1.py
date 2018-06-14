# Copyright (C) 2010,2011  Chris Lalancette <clalance@redhat.com>
# Copyright (C) 2012-2017  Chris Lalancette <clalancette@gmail.com>

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
RHEL-2.1 installation
"""

import oz.OzException
import oz.RedHat

versions = ["GOLD", "U2", "U3", "U4", "U5", "U6"]


class RHEL21Guest(oz.RedHat.RedHatFDGuest):
    """
    Class for RHEL-2.1 GOLD, U2, U3, U4, U5, and U6 installation.
    """
    def __init__(self, tdl, config, auto, output_disk, netdev, diskbus,
                 macaddress):
        oz.RedHat.RedHatFDGuest.__init__(self, tdl, config, auto, output_disk,
                                         netdev, diskbus, macaddress)

    def get_auto_path(self):
        """
        Method to create the correct path to the RHEL 2.1 kickstart file.
        """
        return oz.ozutil.generate_full_auto_path("RHEL2.1.auto")


def get_class(tdl, config, auto, output_disk=None, netdev=None, diskbus=None,
              macaddress=None):
    """
    Factory method for RHEL-2.1 installs.
    """
    if tdl.update in versions:
        if netdev is None:
            netdev = 'pcnet'
        return RHEL21Guest(tdl, config, auto, output_disk, netdev, diskbus,
                           macaddress)


def get_supported_string():
    """
    Return supported versions as a string.
    """
    return "RHEL 2.1: " + ", ".join(versions)
