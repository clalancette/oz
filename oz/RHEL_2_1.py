# Copyright (C) 2010,2011,2012  Chris Lalancette <clalance@redhat.com>

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

import oz.RedHat
import oz.OzException

class RHEL21Guest(oz.RedHat.RedHatFDGuest):
    """
    Class for RHEL-2.1 GOLD, U2, U3, U4, U5, and U6 installation.
    """
    def __init__(self, tdl, config, auto, output_disk):
        oz.RedHat.RedHatFDGuest.__init__(self, tdl, config, auto, output_disk,
                                         "rhel-2.1-jeos.ks", "pcnet")

def get_class(tdl, config, auto, output_disk=None):
    """
    Factory method for RHEL-2.1 installs.
    """
    if tdl.update in ["GOLD", "U2", "U3", "U4", "U5", "U6"]:
        return RHEL21Guest(tdl, config, auto, output_disk)
